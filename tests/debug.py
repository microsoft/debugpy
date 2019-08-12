# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals


import collections
import itertools
import os
import psutil
import py.path
import subprocess
import sys
import tests

import ptvsd
from ptvsd.common import compat, fmt, log, messaging
from tests import code, watchdog, helpers
from tests.patterns import some
from tests.timeline import Timeline, Event, Request, Response

StopInfo = collections.namedtuple(
    "StopInfo", ["body", "frames", "thread_id", "frame_id"]
)

PTVSD_DIR = py.path.local(ptvsd.__file__) / ".."
PTVSD_ADAPTER_DIR = PTVSD_DIR / "adapter"

# Added to the environment variables of every new debug.Session - after copying
# os.environ(), but before setting any session-specific variables.
PTVSD_ENV = {}

counter = itertools.count(1)
WAIT_TIMEOUT_FOR_DA = 5

# Normalize args to either bytes or unicode, depending on Python version.
# Assume that values are filenames - it's usually either that, or numbers.
make_filename = compat.filename_bytes if sys.version_info < (3,) else compat.filename


def kill_process_tree(process):
    log.info("Killing {0} process tree...", process.pid)

    procs = [process]
    try:
        procs += process.children(recursive=True)
    except Exception:
        pass

    for p in procs:
        log.warning(
            "Killing {0}process (pid={1})",
            "" if p.pid == process.pid else "child ",
            p.pid,
        )
        try:
            p.kill()
        except psutil.NoSuchProcess:
            pass
        except Exception:
            log.exception()
    log.info("Killed {0} process tree", process.pid)


class Session(object):
    def __init__(self, start_method, log_dir=None, client_id="vscode", backchannel=False):
        watchdog.start()
        self.id = next(counter)
        self.log_dir = log_dir
        self.start_method = start_method(self)
        self.client_id = client_id

        self.timeline = Timeline(
            ignore_unobserved=[
                Event("output"),
                Event("thread", some.dict.containing({"reason": "exited"})),
                Event("module"),
                Event("continued"),
            ]
            + self.start_method.get_ignored()
        )
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

        self.backchannel = helpers.BackChannel(self) if backchannel else None

    def __str__(self):
        return fmt("ptvsd-{0}", self.id)

    def __enter__(self):
        self._setup_adapter_and_channel()
        self._handshake()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            # Log the error, in case another one happens during shutdown.
            log.exception(exc_info=(exc_type, exc_val, exc_tb))
        self._stop_debug_adapter()

    @property
    def process(self):
        return self.start_method.debugee_process

    @property
    def ignore_unobserved(self):
        return self.timeline.ignore_unobserved

    @ignore_unobserved.setter
    def ignore_unobserved(self, value):
        self.timeline.ignore_unobserved = value

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
            pid = event.body["processId"]
            watchdog.register_spawn(pid, fmt("{0}-subprocess-{1}", self, pid))
        self.timeline.record_event(event, block=False)

    def _process_request(self, request):
        self.timeline.record_request(request, block=False)
        if request.command == "runInTerminal":
            self.start_method.run_in_terminal(request)

    def _process_response(self, request, response):
        self.timeline.record_response(request, response, block=False)
        if request.command == "disconnect":
            # Stop the message loop, since the ptvsd is going to close the connection
            # from its end shortly after sending this event, and no further messages
            # are expected.
            log.info(
                'Received "disconnect" response from {0}; stopping message processing.',
                "ptvsd.adapter",
            )
            try:
                self.channel.close()
            except Exception:
                pass

    def _setup_adapter_and_channel(self):
        args = [sys.executable, PTVSD_ADAPTER_DIR]

        if self.log_dir is not None:
            args += ["--log-dir", self.log_dir]

        args = [make_filename(s) for s in args]

        log.info(
            "Spawning adapter {0}:\n\n{1}", self, "\n".join((repr(s) for s in args))
        )
        self.adapter_process = subprocess.Popen(
            args, bufsize=0, stdin=subprocess.PIPE, stdout=subprocess.PIPE
        )
        self.psutil_adapter_process = psutil.Process(self.adapter_process.pid)
        log.info("Spawned adapter {0} with pid={1}", self, self.adapter_process.pid)
        watchdog.register_spawn(self.adapter_process.pid, fmt("ptvsd.adapter-{0}", self.id))

        stream = messaging.JsonIOStream.from_process(
            self.adapter_process, name=str(self)
        )
        handlers = messaging.MessageHandlers(
            request=self._process_request, event=self._process_event
        )
        self.channel = messaging.JsonMessageChannel(stream, handlers)
        self.channel.start()

    def _stop_debug_adapter(self):
        self.channel.close()
        self.timeline.finalize()
        self.timeline.close()

        log.info(
            "Waiting for debug adapter with pid={0} to exit.", self.adapter_process.pid
        )
        self.adapter_process.wait()
        watchdog.unregister_spawn(self.adapter_process.pid, "ptvsd.adapter")

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
            }
        ).wait_for_response()

    def configure(self, run_as, target, env=os.environ.copy(), **kwargs):
        env.update(PTVSD_ENV)
        if "PYTHONPATH" in env:
            env["PYTHONPATH"] += os.pathsep + (tests.root / "DEBUGGEE_PYTHONPATH").strpath
        else:
            env["PYTHONPATH"] = (tests.root / "DEBUGGEE_PYTHONPATH").strpath
        env["PTVSD_SESSION_ID"] = str(self.id)

        if self.backchannel is not None:
            self.backchannel.listen()
            env['PTVSD_BACKCHANNEL_PORT'] = str(self.backchannel.port)

        log_to_file = (self.log_dir is not None) or kwargs.get("logToFile", False)

        self.start_method.configure(
            run_as, target, env=env, logToFile=log_to_file, **kwargs
        )

    def start_debugging(self):
        self.start_method.start_debugging()

    def request_continue(self):
        self.request("continue", freeze=False)

    def request_disconnect(self):
        self.request("disconnect", freeze=False)

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
        def get_marked_line_numbers():
            try:
                return get_marked_line_numbers.cached
            except AttributeError:
                get_marked_line_numbers.cached = code.get_marked_line_numbers(path)
                return get_marked_line_numbers()

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
        ).get("breakpoints", [])

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
                Response(Request("stackTrace"))
            )
            assert stackTrace_responses, (
                "get_variables() without frame_id requires at least one response "
                'to a "stackTrace" request in the timeline.'
            )
            stack_trace = stackTrace_responses[-1].body
            frame_id = stack_trace["stackFrames"][0]["id"]

        scopes = self.request("scopes", {"frameId": frame_id})["scopes"]
        assert len(scopes) > 0

        variables = self.request(
            "variables", {"variablesReference": scopes[0]["variablesReference"]}
        )["variables"]

        variables = collections.OrderedDict(((v["name"], v) for v in variables))
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
        stopped_event = self.wait_for_next(
            Event("stopped", some.dict.containing({"reason": reason}))
        )
        stopped = stopped_event.body

        if expected_text is not None:
            assert expected_text == stopped["text"]

        if expected_description is not None:
            assert expected_description == stopped["description"]

        tid = stopped["threadId"]
        assert tid == some.int

        assert stopped["allThreadsStopped"]
        if stopped["reason"] not in ["step", "exception", "breakpoint", "entry"]:
            assert stopped["preserveFocusHint"]

        stack_trace = self.request("stackTrace", arguments={"threadId": tid})
        frames = stack_trace["stackFrames"] or []
        assert len(frames) == stack_trace["totalFrames"]

        if expected_frames:
            assert len(expected_frames) <= len(frames)
            assert expected_frames == frames[0: len(expected_frames)]

        fid = frames[0]["id"]
        assert fid == some.int

        return StopInfo(stopped, frames, tid, fid)

    def wait_for_next_event(self, event, body=some.object):
        return self.timeline.wait_for_next(Event(event, body)).body

    def output(self, category):
        """Returns all output of a given category as a single string, assembled from
        all the "output" events received for that category so far.
        """
        events = self.all_occurrences_of(
            Event("output", some.dict.containing({"category": category}))
        )
        return "".join(event.body["output"] for event in events)

    def captured_stdout(self, encoding=None):
        return self.start_method.captured_output.stdout(encoding)

    def captured_stderr(self, encoding=None):
        return self.start_method.captured_output.stderr(encoding)

    def stop_debugging(self, **kwargs):
        self.start_method.stop_debugging(**kwargs)

        if self.backchannel:
            self.backchannel.close()
            self.backchannel = None

        self.request_disconnect()
