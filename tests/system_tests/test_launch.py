import os
import os.path
from textwrap import dedent
import unittest

import ptvsd
from ptvsd.wrapper import INITIALIZE_RESPONSE  # noqa
from tests.helpers.debugclient import EasyDebugClient as DebugClient
from tests.helpers.script import find_line
from tests.helpers.vsc import Response, Event

from . import (
    _strip_newline_output_events,
    lifecycle_handshake,
    LifecycleTestsBase,
)

ROOT = os.path.dirname(os.path.dirname(ptvsd.__file__))
PORT = 9876


class FileLifecycleTests(LifecycleTestsBase):
    def create_source_file(self, file_name, source):
        return self.write_script(file_name, source)

    def get_cwd(self):
        return None

    def find_line(self, filepath, label):
        with open(filepath) as scriptfile:
            script = scriptfile.read()
        return find_line(script, label)

    def get_test_info(self, source):
        filepath = self.create_source_file("spam.py", source)
        env = None
        expected_module = filepath
        argv = [filepath]
        return ("spam.py", filepath, env, expected_module, False, argv,
                self.get_cwd())

    def find_events(self, responses, event, condition=lambda x: True):
        return list(
            response for response in responses if isinstance(response, Event)
            and response.event == event and condition(response.body))  # noqa

    def find_responses(self, responses, command, condition=lambda x: True):
        return list(
                    response for response in responses
                    if isinstance(response, Response) and
                    response.command == command and
                    condition(response.body))

    def fix_module_events(self, responses):
        module_events = self.find_events(responses, 'module')  # noqa
        # Ensure package is None, changes based on version of Python.
        module_events[0].body["module"]["package"] = None
        self.remove_messages(responses, module_events[1:])

    def fix_stack_traces(self, responses, keep_frame_count=1):
        stack_trace = self.find_responses(responses, 'stackTrace')[0]
        stack_frames = stack_trace.body.get("stackFrames")
        # Ignore non-user stack trace.
        del stack_frames[keep_frame_count:len(stack_frames)]
        stack_trace.body["totalFrames"] = keep_frame_count

    def fix_paths(self, responses):
        for msg in self.find_events(responses, 'module'):
            msg.body["module"]["path"] = self.fix_path(msg.body["module"]["path"]) # noqa
        for msg in self.find_responses(responses, 'stackTrace'):
            for frame in msg.body["stackFrames"]:
                frame["source"]["path"] = self.fix_path(frame["source"]["path"]) # noqa

    def fix_path(self, path):
        # Sometimes, the temp paths on mac get prefixed with /private/
        # So, during creation of the file its in /var/, but when debugging,
        # paths CAN soemtimes get returned with the /private/ prefix.
        # Here we just remove them.
        if path.startswith('/private/'):
            return path[len('/private'):]

    def remove_messages(self, responses, messages):
        for msg in messages:
            responses.remove(msg)

    def test_with_output(self):
        source = dedent("""
            import sys
            sys.stdout.write('ok')
            sys.stderr.write('ex')
            """)
        options = {"debugOptions": ["RedirectOutput"]}
        (filename, filepath, env, expected_module, is_module, argv,
         cwd) = self.get_test_info(source)

        with DebugClient(port=PORT) as editor:
            adapter, session = editor.host_local_debugger(
                argv, env=env, cwd=cwd)
            with session.wait_for_event("exited"):
                with session.wait_for_event("thread"):
                    (
                        req_initialize,
                        req_launch,
                        req_config,
                        _,
                        _,
                        _,
                    ) = lifecycle_handshake(
                        session, "launch", options=options)

            adapter.wait()

        # Skipping the 'thread exited' and 'terminated' messages which
        # may appear randomly in the received list.
        received = list(_strip_newline_output_events(session.received))
        self.assert_received(
            received[:-3],
            [
                self.new_version_event(session.received),
                self.new_response(req_initialize, **INITIALIZE_RESPONSE),
                self.new_event("initialized"),
                self.new_response(req_launch),
                self.new_response(req_config),
                self.new_event(
                    "process", **{
                        "isLocalProcess": True,
                        "systemProcessId": adapter.pid,
                        "startMethod": "launch",
                        "name": expected_module,
                    }),
                self.new_event("thread", reason="started", threadId=1),
                self.new_event("output", category="stdout", output="ok"),
                self.new_event("output", category="stderr", output="ex"),
            ],
        )

    def test_with_arguments(self):
        source = dedent("""
            import sys
            print(len(sys.argv))
            for arg in sys.argv:
                print(arg)
            """)
        options = {"debugOptions": ["RedirectOutput"]}
        (filename, filepath, env, expected_module, is_module, argv,
         cwd) = self.get_test_info(source)

        with DebugClient(port=PORT) as editor:
            adapter, session = editor.host_local_debugger(
                argv=argv + ["1", "Hello", "World"], env=env, cwd=cwd)
            with session.wait_for_event("exited"):
                with session.wait_for_event("thread"):
                    (
                        req_initialize,
                        req_launch,
                        req_config,
                        _,
                        _,
                        _,
                    ) = lifecycle_handshake(
                        session, "launch", options=options)

            adapter.wait()

        # Skipping the 'thread exited' and 'terminated' messages which
        # may appear randomly in the received list.
        received = list(_strip_newline_output_events(session.received))
        self.assert_received(
            received[:-3],
            [
                self.new_version_event(session.received),
                self.new_response(req_initialize, **INITIALIZE_RESPONSE),
                self.new_event("initialized"),
                self.new_response(req_launch),
                self.new_response(req_config),
                self.new_event(
                    "process", **{
                        "isLocalProcess": True,
                        "systemProcessId": adapter.pid,
                        "startMethod": "launch",
                        "name": expected_module,
                    }),
                self.new_event("thread", reason="started", threadId=1),
                self.new_event("output", category="stdout", output="4"),
                self.new_event(
                    "output", category="stdout", output=expected_module),
                self.new_event("output", category="stdout", output="1"),
                self.new_event("output", category="stdout", output="Hello"),
                self.new_event("output", category="stdout", output="World"),
            ],
        )

    def test_with_break_points(self):
        source = dedent("""
            a = 1
            b = 2
            # <Token>
            c = 3
            """)
        (filename, filepath, env, expected_module, is_module, argv,
         cwd) = self.get_test_info(source)

        bp_line = self.find_line(filepath, 'Token')
        breakpoints = [{
            "source": {
                "path": filepath
            },
            "breakpoints": [{
                "line": bp_line
            }]
        }]

        with DebugClient(port=PORT, connecttimeout=3.0) as editor:
            adapter, session = editor.host_local_debugger(
                argv, env=env, cwd=cwd)
            with session.wait_for_event("terminated"):
                with session.wait_for_event("stopped") as result:
                    (
                        req_initialize,
                        req_launch,
                        req_config,
                        reqs_bps,
                        _,
                        _,
                    ) = lifecycle_handshake(
                        session, "launch", breakpoints=breakpoints)
                req_bps, = reqs_bps  # There should only be one.
                tid = result["msg"].body["threadId"]

                req_stacktrace = session.send_request(
                    "stackTrace", threadId=tid)

                with session.wait_for_event("continued"):
                    req_continue = session.send_request(
                        "continue", threadId=tid)

            adapter.wait()

        received = list(_strip_newline_output_events(session.received))

        # Cleanup.
        self.fix_module_events(received)
        self.fix_stack_traces(received)

        # Skipping the 'thread exited' and 'terminated' messages which
        # may appear randomly in the received list.
        self.assert_received(
            received[:-3],
            [
                self.new_version_event(session.received),
                self.new_response(req_initialize, **INITIALIZE_RESPONSE),
                self.new_event("initialized"),
                self.new_response(req_launch),
                self.new_response(
                    req_bps, **{
                        "breakpoints": [{
                            "id": 1,
                            "line": bp_line,
                            "verified": True
                        }]
                    }),
                self.new_response(req_config),
                self.new_event(
                    "process", **{
                        "isLocalProcess": True,
                        "systemProcessId": adapter.pid,
                        "startMethod": "launch",
                        "name": expected_module,
                    }),
                self.new_event("thread", reason="started", threadId=tid),
                self.new_event(
                    "stopped",
                    reason="breakpoint",
                    threadId=tid,
                    text=None,
                    description=None,
                ),
                self.new_event(
                    "module",
                    module={
                        "id": 1,
                        "name": "__main__",
                        "path": filepath,
                        "package": None,
                    },
                    reason="new",
                ),
                self.new_response(
                    req_stacktrace,
                    seq=11,
                    **{
                        "totalFrames":
                        1,
                        "stackFrames": [{
                            "id": 1,
                            "name": "<module>",
                            "source": {
                                "path": filepath,
                                "sourceReference": 0
                            },
                            "line": bp_line,
                            "column": 1,
                        }],
                    }),
                self.new_response(req_continue, seq=12),
                self.new_event("continued", seq=13, threadId=tid),
            ],
        )

    @unittest.skip('Needs fixing')
    def test_with_break_points_across_files(self):
        source = dedent("""
            from . import bar
            def foo():
                # <Token>
                bar.do_something()
            foo()
            """)
        (filename, filepath, env, expected_module, is_module, argv,
         cwd) = self.get_test_info(source)
        foo_line = self.find_line(filepath, 'Token')

        source = dedent("""
            def do_something():
                # <Token>
                print("inside bar")
            """)
        bar_filepath = self.create_source_file("bar.py", source)
        bp_line = self.find_line(bar_filepath, 'Token')
        breakpoints = [{
            "source": {
                "path": bar_filepath
            },
            "breakpoints": [{
                "line": bp_line
            }],
            "lines": [bp_line]
        }]

        with DebugClient(port=PORT, connecttimeout=3.0) as editor:
            adapter, session = editor.host_local_debugger(
                argv, env=env, cwd=cwd)
            with session.wait_for_event("terminated"):
                with session.wait_for_event("stopped") as result:
                    (
                        req_initialize,
                        req_launch,
                        req_config,
                        reqs_bps,
                        _,
                        _,
                    ) = lifecycle_handshake(
                        session, "launch", breakpoints=breakpoints)

                req_bps, = reqs_bps  # There should only be one.
                tid = result["msg"].body["threadId"]

                req_stacktrace = session.send_request(
                    "stackTrace", threadId=tid)

                with session.wait_for_event("continued"):
                    req_continue = session.send_request(
                        "continue", threadId=tid)

            adapter.wait()

        received = list(_strip_newline_output_events(session.received))

        # Cleanup.
        self.fix_module_events(received)
        self.fix_stack_traces(received, 2)
        self.fix_paths(received)

        # Skipping the 'thread exited' and 'terminated' messages which
        # may appear randomly in the received list.
        self.assert_received(
            received[:-3],
            [
                self.new_version_event(session.received),
                self.new_response(req_initialize, **INITIALIZE_RESPONSE),
                self.new_event("initialized"),
                self.new_response(req_launch),
                self.new_response(
                    req_bps, **{
                        "breakpoints": [{
                            "id": 1,
                            "line": bp_line,
                            "verified": True
                        }]
                    }),
                self.new_response(req_config),
                self.new_event(
                    "process", **{
                        "isLocalProcess": True,
                        "systemProcessId": adapter.pid,
                        "startMethod": "launch",
                        "name": expected_module,
                    }),
                self.new_event("thread", reason="started", threadId=tid),
                self.new_event(
                    "stopped",
                    reason="breakpoint",
                    threadId=tid,
                    text=None,
                    description=None,
                ),
                self.new_event(
                    "module",
                    module={
                        "id": 1,
                        "name": "mymod.bar" if is_module else "bar",
                        "path": None if is_module else bar_filepath,
                        "package": None,
                    },
                    reason="new",
                ),
                self.new_response(
                    req_stacktrace,
                    seq=12,
                    **{
                        "totalFrames": 2,
                        "stackFrames": [{
                            "id": 1,
                            "name": "do_something",
                            "source": {
                                "path": None if is_module else bar_filepath,
                                "sourceReference": 0
                            },
                            "line": bp_line,
                            "column": 1,
                        }, {
                            "id": 2,
                            "name": "foo",
                            "source": {
                                "path": None,
                                "sourceReference": 0
                            },
                            "line": foo_line,
                            "column": 1,
                        }],
                    }),
                self.new_response(req_continue, seq=13),
                self.new_event("continued", seq=14, threadId=tid),
            ],
        )

    def test_with_log_points(self):
        source = dedent("""
            print('foo')
            a = 1
            for i in range(2):
                # <Token>
                b = i
            print('bar')
            """)
        (filename, filepath, env, expected_module, is_module, argv,
         cwd) = self.get_test_info(source)
        bp_line = self.find_line(filepath, 'Token')
        breakpoints = [{
            "source": {
                "path": filepath,
                "name": filename
            },
            "breakpoints": [{
                "line": bp_line,
                "logMessage": "{a + i}"
            }],
            "lines": [bp_line]
        }]
        options = {"debugOptions": ["RedirectOutput"]}

        with DebugClient(port=PORT, connecttimeout=3.0) as editor:
            adapter, session = editor.host_local_debugger(
                argv, env=env, cwd=cwd)
            with session.wait_for_event("terminated"):
                (
                    req_initialize,
                    req_launch,
                    req_config,
                    reqs_bps,
                    _,
                    _,
                ) = lifecycle_handshake(
                    session,
                    "launch",
                    breakpoints=breakpoints,
                    options=options)
                req_bps, = reqs_bps  # There should only be one.

            adapter.wait()

        # Skipping the 'thread exited' and 'terminated' messages which
        # may appear randomly in the received list.
        received = list(_strip_newline_output_events(session.received))
        self.assert_received(
            received[:-3],
            [
                self.new_version_event(session.received),
                self.new_response(req_initialize, **INITIALIZE_RESPONSE),
                self.new_event("initialized"),
                self.new_response(req_launch),
                self.new_response(
                    req_bps, **{
                        "breakpoints": [{
                            "id": 1,
                            "line": bp_line,
                            "verified": True
                        }]
                    }),
                self.new_response(req_config),
                self.new_event(
                    "process", **{
                        "isLocalProcess": True,
                        "systemProcessId": adapter.pid,
                        "startMethod": "launch",
                        "name": expected_module,
                    }),
                self.new_event("thread", reason="started", threadId=1),
                self.new_event("output", category="stdout", output="foo"),
                self.new_event(
                    "output", category="stdout",
                    output="1" + os.linesep),  # noqa
                self.new_event(
                    "output", category="stdout",
                    output="2" + os.linesep),  # noqa
                self.new_event("output", category="stdout", output="bar"),
            ],
        )

    def test_with_conditional_break_points(self):
        source = dedent("""
            a = 1
            b = 2
            for i in range(5):
                # <Token>
                print(i)
            """)
        (filename, filepath, env, expected_module, is_module, argv,
         cwd) = self.get_test_info(source)
        bp_line = self.find_line(filepath, 'Token')
        breakpoints = [{
            "source": {
                "path": filepath,
                "name": filename
            },
            "breakpoints": [{
                "line": bp_line,
                "condition": "i == 2"
            }],
            "lines": [bp_line]
        }]
        options = {"debugOptions": ["RedirectOutput"]}

        with DebugClient(port=PORT, connecttimeout=3.0) as editor:
            adapter, session = editor.host_local_debugger(
                argv, env=env, cwd=cwd)
            with session.wait_for_event("terminated"):
                with session.wait_for_event("stopped") as result:
                    (
                        req_initialize,
                        req_launch,
                        req_config,
                        reqs_bps,
                        _,
                        _,
                    ) = lifecycle_handshake(
                        session,
                        "launch",
                        breakpoints=breakpoints,
                        options=options)
                req_bps, = reqs_bps  # There should only be one.
                tid = result["msg"].body["threadId"]

                # with session.wait_for_response("stopped") as result:
                req_stacktrace = session.send_request(
                    "stackTrace", threadId=tid, wait=True)

                with session.wait_for_event("continued"):
                    req_continue = session.send_request(
                        "continue", threadId=tid)

            adapter.wait()

        received = list(_strip_newline_output_events(session.received))

        # Cleanup.
        self.fix_module_events(received)
        self.fix_stack_traces(received)

        # Skipping the 'thread exited' and 'terminated' messages which
        # may appear randomly in the received list.
        self.assert_received(
            received[:-3],
            [
                self.new_version_event(session.received),
                self.new_response(req_initialize, **INITIALIZE_RESPONSE),
                self.new_event("initialized"),
                self.new_response(req_launch),
                self.new_response(
                    req_bps, **{
                        "breakpoints": [{
                            "id": 1,
                            "line": bp_line,
                            "verified": True
                        }]
                    }),
                self.new_response(req_config),
                self.new_event(
                    "process", **{
                        "isLocalProcess": True,
                        "systemProcessId": adapter.pid,
                        "startMethod": "launch",
                        "name": expected_module,
                    }),
                self.new_event("thread", reason="started", threadId=tid),
                self.new_event("output", category="stdout", output="0"),
                self.new_event("output", category="stdout", output="1"),
                self.new_event(
                    "stopped",
                    reason="breakpoint",
                    threadId=tid,
                    text=None,
                    description=None,
                ),
                self.new_event(
                    "module",
                    module={
                        "id": 1,
                        "name": "__main__",
                        "path": filepath,
                        "package": None,
                    },
                    reason="new",
                ),
                self.new_response(
                    req_stacktrace,
                    seq=13,
                    **{
                        "totalFrames":
                        1,
                        "stackFrames": [{
                            "id": 1,
                            "name": "<module>",
                            "source": {
                                "path": filepath,
                                "sourceReference": 0
                            },
                            "line": bp_line,
                            "column": 1,
                        }],
                    }),
                self.new_response(req_continue, seq=14),
                self.new_event("continued", seq=15, threadId=tid),
                self.new_event(
                    "output", category="stdout", output="2", seq=16),  # noqa
                self.new_event(
                    "output", category="stdout", output="3", seq=17),  # noqa
                self.new_event(
                    "output", category="stdout", output="4", seq=18),  # noqa
            ],
        )

    @unittest.skip("termination needs fixing")
    def test_terminating_program(self):
        source = dedent("""
            import time

            while True:
                time.sleep(0.1)
            """)
        (filename, filepath, env, expected_module, argv,
         module_name) = self.get_test_info(source)

        with DebugClient(port=PORT, connecttimeout=3.0) as editor:
            adapter, session = editor.host_local_debugger(argv)
            with session.wait_for_event("terminated"):
                (req_initialize, req_launch, req_config, _, _,
                 _) = lifecycle_handshake(  # noqa
                     session, "launch")

                session.send_request("disconnect")

            adapter.wait()


class FileWithCWDLifecycleTests(FileLifecycleTests):
    def get_cwd(self):
        return os.path.dirname(__file__)


# class ModuleLifecycleTests(FileLifecycleTests):
#     def create_source_file(self, file_name, source):
#         return self.write_script(os.path.join('mymod', file_name), source)

#     def get_test_info(self, source):
#         module_name = "mymod"
#         self.workspace.ensure_dir(module_name)
#         self.create_source_file("__main__.py", "")

#         filepath = self.create_source_file("__init__.py", source)
#         env = {"PYTHONPATH": os.path.dirname(os.path.dirname(filepath))}
#         expected_module = module_name + ":"
#         argv = ["-m", module_name]

#         return ("__init__.py", filepath, env, expected_module, True, argv,
#                 self.get_cwd())


# class ModuleWithCWDLifecycleTests(ModuleLifecycleTests,
#                                   FileWithCWDLifecycleTests):  # noqa
#     def get_cwd(self):
#         return os.path.dirname(__file__)
