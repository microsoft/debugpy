# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, division, print_function, unicode_literals

import collections
import itertools
import os
import psutil
import subprocess
import sys

from ptvsd.common import compat, fmt, json, log, messaging
from ptvsd.common.compat import unicode
import tests
from tests import code, debug, timeline, watchdog
from tests.debug import comms, output
from tests.patterns import some


StopInfo = collections.namedtuple(
    "StopInfo", ["body", "frames", "thread_id", "frame_id"]
)


class Session(object):
    counter = itertools.count(1)

    _ignore_unobserved = [
        timeline.Event("module"),
        timeline.Event("continued"),
        timeline.Event("exited"),
        timeline.Event("terminated"),
        timeline.Event("thread", some.dict.containing({"reason": "started"})),
        timeline.Event("thread", some.dict.containing({"reason": "exited"})),
        timeline.Event("output", some.dict.containing({"category": "stdout"})),
        timeline.Event("output", some.dict.containing({"category": "stderr"})),
        timeline.Event("output", some.dict.containing({"category": "console"})),
    ]

    def __init__(
        self, start_method, log_dir=None, client_id="vscode", backchannel=False
    ):
        watchdog.start()
        self.id = next(Session.counter)
        self.log_dir = log_dir
        self.start_method = start_method(self)
        self.client_id = client_id

        self.timeline = timeline.Timeline(str(self))
        self.ignore_unobserved.extend(self._ignore_unobserved)
        self.ignore_unobserved.extend(self.start_method.ignore_unobserved)

        self.adapter_process = None
        self.channel = None
        self.backchannel = comms.BackChannel(self) if backchannel else None
        self.scratchpad = comms.ScratchPad(self)

        # Expose some common members of timeline directly - these should be the ones
        # that are the most straightforward to use, and are difficult to use incorrectly.
        # Conversely, most tests should restrict themselves to this subset of the API,
        # and avoid calling members of timeline directly unless there is a good reason.
        self.new = self.timeline.new
        self.observe = self.timeline.observe
        self.wait_for_next = self.timeline.wait_for_next
        self.proceed = self.timeline.proceed
        self.expect_new = self.timeline.expect_new
        self.expect_realized = self.timeline.expect_realized
        self.all_occurrences_of = self.timeline.all_occurrences_of
        self.observe_all = self.timeline.observe_all

    def __str__(self):
        return fmt("ptvsd-{0}", self.id)

    @property
    def adapter_id(self):
        return fmt("adapter-{0}", self.id)

    @property
    def debuggee_id(self):
        return fmt("debuggee-{0}", self.id)

    def __enter__(self):
        self._start_adapter()
        self._handshake()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            # Only wait for debuggee if there was no exception in the test - if there
            # was one, the debuggee might still be waiting for further requests.
            self.start_method.wait_for_debuggee()
        else:
            # Log the error, in case another one happens during shutdown.
            log.exception(exc_info=(exc_type, exc_val, exc_tb))

        if exc_type is None:
            self.disconnect()
            self.timeline.close()
        else:
            # If there was an exception, don't try to send any more messages to avoid
            # spamming log with irrelevant entries - just close the channel and kill
            # the adapter process immediately. Don't close or finalize the timeline,
            # either, since it'll have unobserved events in it.
            self.disconnect(force=True)
            if self.adapter_process is not None:
                try:
                    self.adapter_process.kill()
                except Exception:
                    pass

        if self.adapter_process is not None:
            log.info(
                "Waiting for {0} with PID={1} to exit.",
                self.adapter_id,
                self.adapter_process.pid,
            )
            self.adapter_process.wait()
            watchdog.unregister_spawn(self.adapter_process.pid, self.adapter_id)
            self.adapter_process = None

        if self.backchannel:
            self.backchannel.close()
            self.backchannel = None

    @property
    def process(self):
        return self.start_method.debuggee_process

    @property
    def pid(self):
        return self.process.pid

    @property
    def ignore_unobserved(self):
        return self.timeline.ignore_unobserved

    @property
    def expected_exit_code(self):
        return self.start_method.expected_exit_code

    @expected_exit_code.setter
    def expected_exit_code(self, value):
        self.start_method.expected_exit_code = value

    def request(self, *args, **kwargs):
        freeze = kwargs.pop("freeze", True)
        raise_if_failed = kwargs.pop("raise_if_failed", True)
        return (
            self.send_request(*args, **kwargs)
            .wait_for_response(freeze=freeze, raise_if_failed=raise_if_failed)
            .body
        )

    def send_request(self, command, arguments=None, proceed=True):
        if self.timeline.is_frozen and proceed:
            self.proceed()

        message = self.channel.send_request(command, arguments)
        request = self.timeline.record_request(message)

        # Register callback after recording the request, so that there's no race
        # between it being recorded, and the response to it being received.
        message.on_response(lambda response: self._process_response(request, response))

        return request

    def _process_event(self, event):
        if event.event == "ptvsd_subprocess":
            pid = event("processId", int)
            watchdog.register_spawn(pid, fmt("{0}-subprocess-{1}", self, pid))
        self.timeline.record_event(event, block=False)

    def _process_request(self, request):
        self.timeline.record_request(request, block=False)
        if request.command == "runInTerminal":
            return self.start_method.run_in_terminal(request)
        else:
            raise request.isnt_valid("not supported")

    def _process_response(self, request, response):
        self.timeline.record_response(request, response, block=False)
        if request.command == "disconnect":
            # Stop the message loop, since the ptvsd is going to close the connection
            # from its end shortly after sending this event, and no further messages
            # are expected.
            log.info(
                'Received "disconnect" response from {0}; stopping message processing.',
                self.adapter_id,
            )
            try:
                self.channel.close()
            except Exception:
                pass

    def _process_disconnect(self):
        self.timeline.mark("disconnect", block=False)

    def _start_adapter(self):
        args = [sys.executable, debug.PTVSD_ADAPTER_DIR]
        if self.log_dir is not None:
            args += ["--log-dir", self.log_dir]
        args = [compat.filename_str(s) for s in args]

        env = os.environ.copy()
        env.update(debug.PTVSD_ENV)
        env = {
            compat.filename_str(k): compat.filename_str(v) for k, v in env.items()
        }

        log.info("Spawning {0}: {1!j}", self.adapter_id, args)
        self.adapter_process = psutil.Popen(
            args, bufsize=0, stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=env
        )
        log.info("Spawned {0} with PID={1}", self.adapter_id, self.adapter_process.pid)
        watchdog.register_spawn(self.adapter_process.pid, self.adapter_id)

        stream = messaging.JsonIOStream.from_process(
            self.adapter_process, name=str(self)
        )
        handlers = messaging.MessageHandlers(
            request=self._process_request,
            event=self._process_event,
            disconnect=self._process_disconnect,
        )
        self.channel = messaging.JsonMessageChannel(stream, handlers)
        self.channel.start()

    def _handshake(self):
        telemetry = self.wait_for_next_event("output")
        assert telemetry == {
            "category": "telemetry",
            "output": "ptvsd.adapter",
            "data": {"version": some.str},
        }

        self.send_request(
            "initialize",
            {
                "pathFormat": "path",
                "clientID": self.client_id,
                # "clientName":"Visual Studio Code",
                "adapterID": "test",
                "linesStartAt1": True,
                "columnsStartAt1": True,
                "supportsVariableType": True,
                "supportsRunInTerminalRequest": True,
                # "supportsMemoryReferences":true,
                # "supportsHandshakeRequest":true,
                # "AdditionalProperties":{}
            },
        ).wait_for_response()

    def configure(self, run_as, target, env=None, **kwargs):
        env = {} if env is None else dict(env)
        env.update(debug.PTVSD_ENV)

        pythonpath = env.get("PYTHONPATH", "")
        if pythonpath:
            pythonpath += os.pathsep
        pythonpath += (tests.root / "DEBUGGEE_PYTHONPATH").strpath
        pythonpath += os.pathsep + (debug.PTVSD_DIR / "..").strpath
        env["PYTHONPATH"] = pythonpath

        env["PTVSD_SESSION_ID"] = str(self.id)

        if self.backchannel is not None:
            self.backchannel.listen()
            env["PTVSD_BACKCHANNEL_PORT"] = str(self.backchannel.port)

        if self.log_dir is not None:
            kwargs["logToFile"] = True

        self.captured_output = output.CaptureOutput(self)
        self.start_method.configure(run_as, target, env=env, **kwargs)

    def start_debugging(self):
        start_request = self.start_method.start_debugging()
        process = self.wait_for_next_event("process", freeze=False)
        assert process == some.dict.containing(
            {
                "startMethod": start_request.command,
                "name": some.str,
                "isLocalProcess": True,
                "systemProcessId": some.int,
            }
        )

    def request_continue(self):
        self.request("continue", freeze=False)

    def set_breakpoints(self, path, lines):
        """Sets breakpoints in the specified file, and returns the list of all the
        corresponding DAP Breakpoint objects in the same order.

        If lines are specified, it should be an iterable in which every element is
        either a line number or a string. If it is a string, then it is translated
        to the corresponding line number via get_marked_line_numbers(path).

        If lines=all, breakpoints will be set on all the marked lines in the file.
        """

        # Don't fetch line markers unless needed - in some cases, the breakpoints
        # might be set in a file that does not exist on disk (e.g. remote attach).
        get_marked_line_numbers = lambda: code.get_marked_line_numbers(path)

        if lines is all:
            lines = get_marked_line_numbers().keys()

        def make_breakpoint(line):
            if isinstance(line, int):
                descr = str(line)
            else:
                marker = line
                line = get_marked_line_numbers()[marker]
                descr = fmt("{0} (@{1})", line, marker)
            bp_log.append((line, descr))
            return {"line": line}

        bp_log = []
        breakpoints = self.request(
            "setBreakpoints",
            {
                "source": {"path": path},
                "breakpoints": [make_breakpoint(line) for line in lines],
            },
        )("breakpoints", json.array())

        bp_log = sorted(bp_log, key=lambda pair: pair[0])
        bp_log = ", ".join((descr for _, descr in bp_log))
        log.info("Breakpoints set in {0}: {1}", path, bp_log)

        return breakpoints

    def get_variables(self, *varnames, **kwargs):
        """Fetches the specified variables from the frame specified by frame_id, or
        from the topmost frame in the last "stackTrace" response if frame_id is not
        specified.

        If varnames is empty, then all variables in the frame are returned. The result
        is an OrderedDict, in which every entry has variable name as the key, and a
        DAP Variable object as the value. The original order of variables as reported
        by the debugger is preserved.

        If varnames is not empty, then only the specified variables are returned.
        The result is a tuple, in which every entry is a DAP Variable object; those
        entries are in the same order as varnames.
        """

        assert self.timeline.is_frozen

        frame_id = kwargs.pop("frame_id", None)
        if frame_id is None:
            stackTrace_responses = self.all_occurrences_of(
                timeline.Response(timeline.Request("stackTrace"))
            )
            assert stackTrace_responses, (
                "get_variables() without frame_id requires at least one response "
                'to a "stackTrace" request in the timeline.'
            )
            stack_trace = stackTrace_responses[-1]
            frame_id = stack_trace.body.get("stackFrames", json.array())[0]("id", int)

        scopes = self.request("scopes", {"frameId": frame_id})("scopes", json.array())
        assert len(scopes) > 0

        variables = self.request(
            "variables", {"variablesReference": scopes[0]("variablesReference", int)}
        )("variables", json.array())

        variables = collections.OrderedDict(
            ((v("name", unicode), v) for v in variables)
        )
        if varnames:
            assert set(varnames) <= set(variables.keys())
            return tuple((variables[name] for name in varnames))
        else:
            return variables

    def get_variable(self, varname, frame_id=None):
        """Same as get_variables(...)[0].
        """
        return self.get_variables(varname, frame_id=frame_id)[0]

    def wait_for_stop(
        self,
        reason=some.str,
        expected_frames=None,
        expected_text=None,
        expected_description=None,
    ):
        stopped = self.wait_for_next_event("stopped")

        expected_stopped = {
            "reason": reason,
            "threadId": some.int,
            "allThreadsStopped": True,
        }
        if expected_text is not None:
            expected_stopped["text"] = expected_text
        if expected_description is not None:
            expected_stopped["description"] = expected_description
        if stopped("reason", unicode) not in [
            "step",
            "exception",
            "breakpoint",
            "entry",
            "goto",
        ]:
            expected_stopped["preserveFocusHint"] = True
        assert stopped == some.dict.containing(expected_stopped)

        tid = stopped("threadId", int)
        stack_trace = self.request("stackTrace", {"threadId": tid})
        frames = stack_trace("stackFrames", json.array()) or []
        assert len(frames) == stack_trace("totalFrames", int)

        if expected_frames:
            assert len(expected_frames) <= len(frames)
            assert expected_frames == frames[0 : len(expected_frames)]

        fid = frames[0]("id", int)
        return StopInfo(stopped, frames, tid, fid)

    def wait_for_next_event(self, event, body=some.object, freeze=True):
        return self.timeline.wait_for_next(
            timeline.Event(event, body), freeze=freeze
        ).body

    def output(self, category):
        """Returns all output of a given category as a single string, assembled from
        all the "output" events received for that category so far.
        """
        events = self.all_occurrences_of(
            timeline.Event("output", some.dict.containing({"category": category}))
        )
        return "".join(event("output", unicode) for event in events)

    def captured_stdout(self, encoding=None):
        return self.captured_output.stdout(encoding)

    def captured_stderr(self, encoding=None):
        return self.captured_output.stderr(encoding)

    def wait_for_disconnect(self):
        self.timeline.wait_for_next(timeline.Mark("disconnect"))

    def disconnect(self, force=False):
        if self.channel is None:
            return

        try:
            if not force:
                self.request("disconnect")
        except messaging.JsonIOError:
            pass
        finally:
            try:
                self.channel.close()
            except Exception:
                pass
            self.channel.wait()
            self.channel = None
