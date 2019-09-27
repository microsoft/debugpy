# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, division, print_function, unicode_literals

import collections
import itertools
import os
import psutil
import py
import subprocess
import sys
import time

import ptvsd.adapter
from ptvsd.common import compat, fmt, json, log, messaging, options, sockets, util
from ptvsd.common.compat import unicode
import tests
from tests import code, timeline, watchdog
from tests.debug import comms, config, output
from tests.patterns import some


DEBUGGEE_PYTHONPATH = tests.root / "DEBUGGEE_PYTHONPATH"


StopInfo = collections.namedtuple(
    "StopInfo", ["body", "frames", "thread_id", "frame_id"]
)


class Session(object):
    """A test debug session. Manages the lifetime of the adapter and the debuggee
    processes, captures debuggee stdio output, establishes a DAP message channel to
    the debuggee, and records all DAP messages in that channel on a Timeline object.

    Must be used in a with-statement for proper cleanup. On successful exit - if no
    exception escapes from the with-statement - the session will:

    1. Invoke wait_for_exit(), unless expected_exit_code is None.
    2. Invoke disconnect().
    3. Wait for the adapter process to exit.
    4. Finalize and closes the timeline

    If the exit is due to an exception, the session will:

    1. Invoke disconnect(force=True).
    2. Kill the debuggee and the adapter processes.

    Example::

        with debug.Session() as session:
            # Neither debuggee nor adapter are spawned yet. Initial configuration.
            session.log_dir = ...
            session.config.update({...})

            with session.launch(...):
                # Debuggee and adapter are spawned, but there is no code executing
                # in the debuggee yet.
                session.set_breakpoints(...)

            # Code is executing in the debuggee.
            session.wait_for_stop(expected_frames=[...])
            assert session.get_variable(...) == ...
            session.request_continue()

        # Session is disconnected from the debuggee, and both the debuggee and the
        # adapter processes have exited.
        assert session.exit_code == ...
    """

    tmpdir = None
    """Temporary directory in which Sessions can create the temp files they need.

    Automatically set to tmpdir for the current test by pytest_fixtures.test_wrapper().
    """

    _counter = itertools.count(1)

    def __init__(self):
        assert Session.tmpdir is not None
        watchdog.start()

        self.id = next(Session._counter)
        log.info("Starting {0}", self)

        self.client_id = "vscode"

        self.debuggee = None
        """psutil.Popen instance for the debuggee process."""

        self.adapter = None
        """psutil.Popen instance for the adapter process."""

        self.channel = None
        """JsonMessageChannel to the adapter."""

        self.captured_output = {"stdout", "stderr"}
        """Before the debuggee is spawned, this is the set of stdio streams that
        should be captured once it is spawned.

        After it is spawned, this is a CapturedOutput object capturing those streams.
        """

        self.backchannel = None
        """The BackChannel object to talk to the debuggee.

        Must be explicitly created with open_backchannel().
        """

        self.scratchpad = comms.ScratchPad(self)
        """The ScratchPad object to talk to the debuggee."""

        self.start_request = None
        """The "launch" or "attach" request that started executing code in this session.
        """

        self.expected_exit_code = 0
        """The expected exit code for the debuggee process.

        If None, the debuggee is not expected to exit when the Session is closed.

        If not None, this is validated against both exit_code and debuggee.returncode.
        """

        self.exit_code = None
        """The actual exit code for the debuggee process, as received from DAP.
        """

        self.config = config.DebugConfig(
            {
                "justMyCode": True,
                "name": "Test",
                "redirectOutput": True,
                "type": "python",
            }
        )
        """The debug configuration for this session."""

        self.log_dir = (
            None
            if options.log_dir is None
            else py.path.local(options.log_dir) / str(self)
        )
        """The log directory for this session. Passed via PTVSD_LOG_DIR to all spawned
        child processes.

        If set to None, PTVSD_LOG_DIR is not automatically added, but tests can still
        provide it manually.
        """

        self.tmpdir = Session.tmpdir / str(self)
        self.tmpdir.ensure(dir=True)

        self.timeline = timeline.Timeline(str(self))
        self.ignore_unobserved.extend(
            [
                timeline.Event("module"),
                timeline.Event("continued"),
                # timeline.Event("exited"),
                # timeline.Event("terminated"),
                timeline.Event("thread", some.dict.containing({"reason": "started"})),
                timeline.Event("thread", some.dict.containing({"reason": "exited"})),
                timeline.Event("output", some.dict.containing({"category": "stdout"})),
                timeline.Event("output", some.dict.containing({"category": "stderr"})),
                timeline.Event("output", some.dict.containing({"category": "console"})),
            ]
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

        spawn_adapter = self.spawn_adapter
        self.spawn_adapter = lambda *args, **kwargs: spawn_adapter(*args, **kwargs)
        self.spawn_adapter.env = util.Env()

        spawn_debuggee = self.spawn_debuggee
        self.spawn_debuggee = lambda *args, **kwargs: spawn_debuggee(*args, **kwargs)
        self.spawn_debuggee.env = util.Env()

    def __str__(self):
        return fmt("Session-{0}", self.id)

    @property
    def adapter_id(self):
        return fmt("Adapter-{0}", self.id)

    @property
    def debuggee_id(self):
        return fmt("Debuggee-{0}", self.id)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.timeline.is_frozen:
            self.timeline.unfreeze()

        # Only wait for exit if there was no exception in the test - if there was one,
        # the debuggee might still be waiting for further requests.
        if exc_type is None:
            # If expected_exit_code is set to None, the debuggee is not expected to
            # exit after this Session is closed (e.g. because another Session will
            # attach to it later on).
            if self.expected_exit_code is not None:
                self.wait_for_exit()
        else:
            # Log the error, in case another one happens during shutdown.
            log.exception(exc_info=(exc_type, exc_val, exc_tb))

        if exc_type is None:
            self.disconnect()
            self.timeline.close()
        else:
            # If there was an exception, don't try to send any more messages to avoid
            # spamming log with irrelevant entries - just close the channel and kill
            # all the processes immediately. Don't close or finalize the timeline,
            # either, since it'll likely have unobserved events in it.
            self.disconnect(force=True)
            if self.adapter is not None:
                try:
                    self.adapter.kill()
                except Exception:
                    pass
            if self.debuggee is not None:
                try:
                    self.debuggee.kill()
                except Exception:
                    pass

        if self.adapter is not None:
            log.info(
                "Waiting for {0} with PID={1} to exit.",
                self.adapter_id,
                self.adapter.pid,
            )
            self.adapter.wait()
            watchdog.unregister_spawn(self.adapter.pid, self.adapter_id)
            self.adapter = None

        if self.backchannel is not None:
            self.backchannel.close()
            self.backchannel = None

    @property
    def ignore_unobserved(self):
        return self.timeline.ignore_unobserved

    def open_backchannel(self):
        assert self.backchannel is None
        self.backchannel = comms.BackChannel(self)
        self.backchannel.listen()
        return self.backchannel

    def _init_log_dir(self):
        if self.log_dir is None:
            return False

        log.info("Logs for {0} will be in {1!j}", self, self.log_dir)
        try:
            self.log_dir.remove()
        except Exception:
            pass
        self.log_dir.ensure(dir=True)

        # Make subsequent calls of this method no-op for the remainder of the session.
        self._init_log_dir = lambda: True
        return True

    def _make_env(self, base_env, codecov=True):
        env = util.Env.snapshot()

        if base_env is not None:
            base_env = dict(base_env)
            python_path = base_env.pop("PYTHONPATH", None)
            if python_path is not None:
                env.prepend_to("PYTHONPATH", python_path)
            env.update(base_env)

        env["PTVSD_TEST_SESSION_ID"] = str(self.id)
        env.prepend_to("PYTHONPATH", DEBUGGEE_PYTHONPATH.strpath)

        if self._init_log_dir():
            env.update(
                {
                    "PTVSD_LOG_DIR": self.log_dir.strpath,
                    "PYDEVD_DEBUG": "True",
                    "PYDEVD_DEBUG_FILE": (self.log_dir / "pydevd.log").strpath,
                }
            )

        if self.backchannel is not None:
            env["PTVSD_TEST_BACKCHANNEL_PORT"] = str(self.backchannel.port)

        return env

    def spawn_debuggee(self, args, cwd=None, exe=sys.executable, debug_me=None):
        assert self.debuggee is None

        args = [exe] + [
            compat.filename_str(s.strpath if isinstance(s, py.path.local) else s)
            for s in args
        ]

        env = self._make_env(self.spawn_debuggee.env, codecov=False)
        env["PTVSD_LISTENER_FILE"] = self.listener_file = self.tmpdir / "listener"
        if debug_me is not None:
            env["PTVSD_TEST_DEBUG_ME"] = debug_me

        log.info(
            "Spawning {0}:\n\n"
            "Current directory: {1!j}\n\n"
            "Command line: {2!j}\n\n"
            "Environment variables: {3!j}\n\n",
            self.debuggee_id,
            cwd,
            args,
            env,
        )
        self.debuggee = psutil.Popen(
            args,
            cwd=cwd,
            env=env.for_popen(),
            bufsize=0,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        log.info("Spawned {0} with PID={1}", self.debuggee_id, self.debuggee.pid)
        watchdog.register_spawn(self.debuggee.pid, self.debuggee_id)

        if self.captured_output:
            self.captured_output = output.CapturedOutput(self)

    def wait_for_enable_attach(self):
        log.info(
            "Waiting for debug server in {0} to open a listener socket...",
            self.debuggee_id,
        )
        while not self.listener_file.check():
            time.sleep(0.1)

    def spawn_adapter(self):
        assert self.adapter is None
        assert self.channel is None

        args = [sys.executable, os.path.dirname(ptvsd.adapter.__file__)]
        env = self._make_env(self.spawn_adapter.env)

        log.info(
            "Spawning {0}:\n\n"
            "Command line: {1!j}\n\n"
            "Environment variables: {2!j}\n\n",
            self.adapter_id,
            args,
            env,
        )
        self.adapter = psutil.Popen(
            args,
            bufsize=0,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            env=env.for_popen(),
        )
        log.info("Spawned {0} with PID={1}", self.adapter_id, self.adapter.pid)
        watchdog.register_spawn(self.adapter.pid, self.adapter_id)

        stream = messaging.JsonIOStream.from_process(self.adapter, name=self.adapter_id)
        self._start_channel(stream)

    def connect_to_adapter(self, address):
        assert self.channel is None

        host, port = address
        log.info("Connecting to {0} at {1}:{2}", self.adapter_id, host, port)
        sock = sockets.create_client()
        sock.connect(address)

        stream = messaging.JsonIOStream.from_socket(sock, name=self.adapter_id)
        self._start_channel(stream)

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
        if command in ("launch", "attach"):
            self.start_request = request

        # Register callback after recording the request, so that there's no race
        # between it being recorded, and the response to it being received.
        message.on_response(lambda response: self._process_response(request, response))

        return request

    def _process_event(self, event):
        occ = self.timeline.record_event(event, block=False)
        if event.event == "exited":
            self.observe(occ)
            self.exit_code = event("exitCode", int)
            assert self.exit_code == self.expected_exit_code
        elif event.event == "ptvsd_subprocess":
            self.observe(occ)
            pid = event("processId", int)
            watchdog.register_spawn(
                pid, fmt("{0}-subprocess-{1}", self.debuggee_id, pid)
            )

    def _process_request(self, request):
        self.timeline.record_request(request, block=False)
        if request.command == "runInTerminal":
            args = request("args", json.array(unicode))
            cwd = request("cwd", ".")
            env = request("env", json.object(unicode))
            try:
                exe = args.pop(0)
                assert not len(self.spawn_debuggee.env)
                self.spawn_debuggee.env = env
                self.spawn_debuggee(args, cwd, exe=exe)
                return {}
            except OSError as exc:
                log.exception('"runInTerminal" failed:')
                raise request.cant_handle(str(exc))
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

    def _start_channel(self, stream):
        handlers = messaging.MessageHandlers(
            request=self._process_request,
            event=self._process_event,
            disconnect=self._process_disconnect,
        )
        self.channel = messaging.JsonMessageChannel(stream, handlers)
        self.channel.start()

        telemetry = self.wait_for_next_event("output")
        assert telemetry == {
            "category": "telemetry",
            "output": "ptvsd.adapter",
            "data": {"version": some.str},
        }

        self.request(
            "initialize",
            {
                "pathFormat": "path",
                "clientID": self.client_id,
                "adapterID": "test",
                "linesStartAt1": True,
                "columnsStartAt1": True,
                "supportsVariableType": True,
                "supportsRunInTerminalRequest": True,
            },
        )

    def all_events(self, event, body=some.object):
        return [
            occ.body
            for occ in self.timeline.all_occurrences_of(timeline.Event(event, body))
        ]

    def output(self, category):
        """Returns all output of a given category as a single string, assembled from
        all the "output" events received for that category so far.
        """
        events = self.all_events("output", some.dict.containing({"category": category}))
        return "".join(event("output", unicode) for event in events)

    def _request_start(self, method):
        self.config.normalize()
        start_request = self.send_request(method, self.config)

        # Depending on whether it's "noDebug" or not, we either get the "initialized"
        # event, or an immediate response to our request.
        self.timeline.wait_until_realized(
            timeline.Event("initialized") | timeline.Response(start_request),
            freeze=True,
        )

        if start_request.response is not None:
            # It was an immediate response - configuration is not possible. Just get
            # the "process" event, and return to caller.
            return self.wait_for_process()

        # We got "initialized" - now we need to yield to the caller, so that it can
        # configure the session before it starts running.
        return self._ConfigurationContextManager(self)

    class _ConfigurationContextManager(object):
        """Handles the start configuration sequence from "initialized" event until
        start_request receives a response.
        """

        def __init__(self, session):
            self.session = session
            self._entered = False

        def __enter__(self):
            self._entered = True
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            self.session.request("configurationDone")
            self.session.start_request.wait_for_response()
            self.session.wait_for_process()

        def __del__(self):
            assert self._entered, (
                "The return value of request_launch() or request_attach() must be "
                "used in a with-statement."
            )

    def request_launch(self):
        if "PYTHONPATH" in self.config.env:
            # If specified, launcher will use it in lieu of PYTHONPATH it inherited
            # from the adapter when spawning debuggee, so we need to adjust again.
            self.config.env.prepend_to("PYTHONPATH", DEBUGGEE_PYTHONPATH.strpath)
        return self._request_start("launch")

    def request_attach(self):
        return self._request_start("attach")

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

    def wait_for_next_event(self, event, body=some.object, freeze=True):
        return self.timeline.wait_for_next(
            timeline.Event(event, body), freeze=freeze
        ).body

    def wait_for_process(self):
        process = self.wait_for_next_event("process", freeze=False)
        assert process == some.dict.containing(
            {
                "startMethod": self.start_request.command,
                "name": some.str,
                "isLocalProcess": True,
                "systemProcessId": some.int,
            }
        )

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

    def wait_for_next_subprocess(self):
        raise NotImplementedError

    def wait_for_disconnect(self):
        self.timeline.wait_until_realized(timeline.Mark("disconnect"), freeze=True)

    def wait_for_exit(self):
        if self.debuggee is not None:
            try:
                self.debuggee.wait()
            except Exception:
                pass
            finally:
                watchdog.unregister_spawn(self.debuggee.pid, self.debuggee_id)

        self.timeline.wait_until_realized(timeline.Event("terminated"))

        # FIXME: "exited" event is not properly reported in attach scenarios at the
        # moment, so the exit code is only checked if it's present.
        if self.start_request.command == "launch":
            assert self.exit_code is not None
        if self.debuggee is not None and self.exit_code is not None:
            assert self.debuggee.returncode == self.exit_code
        return self.exit_code

    def captured_stdout(self, encoding=None):
        assert self.debuggee is not None
        return self.captured_output.stdout(encoding)

    def captured_stderr(self, encoding=None):
        assert self.debuggee is not None
        return self.captured_output.stderr(encoding)

    def disconnect(self, force=False):
        if self.channel is None:
            return

        try:
            if not force:
                self.request("disconnect")
                self.timeline.wait_until_realized(timeline.Event("terminated"))
        except messaging.JsonIOError:
            pass
        finally:
            try:
                self.channel.close()
            except Exception:
                pass
            self.channel.wait()
            self.channel = None
