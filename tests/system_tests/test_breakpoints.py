import os
import os.path
import unittest

from ptvsd.wrapper import INITIALIZE_RESPONSE  # noqa

from . import (_strip_newline_output_events, lifecycle_handshake,
               LifecycleTestsBase, DebugInfo, ROOT, PORT)

TEST_FILES_DIR = os.path.join(ROOT, 'tests', 'resources', 'system_tests',
                              'test_breakpoints')


class LaunchLifecycleTests(LifecycleTestsBase):
    # def test_with_arguments(self):
    #     source = dedent("""
    #         import sys
    #         print(len(sys.argv))
    #         for arg in sys.argv:
    #             print(arg)
    #         """)
    #     options = {"debugOptions": ["RedirectOutput"]}
    #     (filename, filepath, env, expected_module, argv,
    #      cwd) = self.get_test_info(source)

    #     with DebugClient(port=PORT, connecttimeout=CONNECT_TIMEOUT) as editor: # noqa
    #         adapter, session = editor.host_local_debugger(
    #             argv=argv + ["1", "Hello", "World"], env=env,
    #             cwd=cwd, timeout=CONNECT_TIMEOUT)
    #         terminated = session.get_awaiter_for_event('terminated')
    #         thread_exit = session.get_awaiter_for_event('thread', lambda msg: msg.body.get("reason", "") == "exited") # noqa
    #         with session.wait_for_event("exited"):
    #             with session.wait_for_event("thread"):
    #                 (
    #                     req_initialize,
    #                     req_launch,
    #                     req_config,
    #                     _,
    #                     _,
    #                     _,
    #                 ) = lifecycle_handshake(
    #                     session, "launch", options=options)

    #         adapter.wait()
    #         Awaitable.wait_all(terminated, thread_exit)

    #     # Skipping the 'thread exited' and 'terminated' messages which
    #     # may appear randomly in the received list.
    #     received = list(_strip_newline_output_events(session.received))
    #     self.assert_contains(
    #         received,
    #         [
    #             self.new_version_event(session.received),
    #             self.new_response(req_initialize.req, **INITIALIZE_RESPONSE),
    #             self.new_event("initialized"),
    #             self.new_response(req_launch.req),
    #             self.new_response(req_config.req),
    #             self.new_event(
    #                 "process", **{
    #                     "isLocalProcess": True,
    #                     "systemProcessId": adapter.pid,
    #                     "startMethod": "launch",
    #                     "name": expected_module,
    #                 }),
    #             self.new_event("thread", reason="started", threadId=1),
    #             self.new_event("output", category="stdout", output="4"),
    #             self.new_event("output", category="stdout", output=expected_module), # noqa
    #             self.new_event("output", category="stdout", output="1"),
    #             self.new_event("output", category="stdout", output="Hello"),
    #             self.new_event("output", category="stdout", output="World"),
    #         ],
    #     )

    def test_with_break_points(self):
        filename = os.path.join(TEST_FILES_DIR, 'output.py')
        cwd = os.path.dirname(filename)
        self.run_test_with_break_points(
            DebugInfo(filename=filename, cwd=cwd), filename, bp_line=3)

    def run_test_with_break_points(self, debug_info, bp_filename, bp_line):
        options = {"debugOptions": ["RedirectOutput"]}
        breakpoints = [{
            "source": {
                "path": bp_filename
            },
            "breakpoints": [{
                "line": bp_line
            }]
        }]

        with self.start_debugging(debug_info) as dbg:
            session = dbg.session
            with session.wait_for_event("stopped") as result:
                (
                    _,
                    req_launch_attach,
                    _,
                    reqs_bps,
                    _,
                    _,
                ) = lifecycle_handshake(
                    session,
                    debug_info.starttype,
                    options=options,
                    breakpoints=breakpoints)

                req_launch_attach.wait()

            req_bps, = reqs_bps  # There should only be one.
            tid = result["msg"].body["threadId"]
            stacktrace = session.send_request("stackTrace", threadId=tid)
            stacktrace.wait()
            session.send_request("continue", threadId=tid)

        received = list(_strip_newline_output_events(session.received))

        self.assertGreaterEqual(stacktrace.resp.body["totalFrames"], 1)
        self.assert_is_subset(
            stacktrace.resp.body,
            {
                # We get Python and PTVSD frames as well.
                # "totalFrames": 2,
                "stackFrames": [{
                    "id": 1,
                    "name": "<module>",
                    "source": {
                        "sourceReference": 0
                    },
                    "line": bp_line,
                    "column": 1,
                }],
            })

        self.assert_contains(
            received,
            [
                self.new_event(
                    "stopped",
                    reason="breakpoint",
                    threadId=tid,
                    text=None,
                    description=None,
                ),
                self.new_event("continued", threadId=tid),
                self.new_event("output", category="stdout", output="yes"),
                self.new_event("output", category="stderr", output="no"),
                self.new_event("exited", exitCode=0),
                self.new_event("terminated"),
            ],
        )

    # def test_with_break_points_across_files(self):
    #     source = dedent("""
    #         def do_something():
    #             # <Token>
    #             print("inside bar")
    #         """)
    #     bar_filepath = self.create_source_file("bar.py", source)
    #     bp_line = self.find_line(bar_filepath, 'Token')

    #     source_module = dedent("""
    #         from . import bar
    #         def foo():
    #             # <Token>
    #             bar.do_something()
    #         foo()
    #         """)
    #     source_file = dedent("""
    #         import bar
    #         def foo():
    #             # <Token>
    #             bar.do_something()
    #         foo()
    #         """)
    #     (filename, filepath, env, expected_module, argv,
    #      cwd) = self.get_test_info(source_module
    #                                if self.IS_MODULE else source_file)  # noqa
    #     foo_line = self.find_line(filepath, 'Token')

    #     breakpoints = [{
    #         "source": {
    #             "path": bar_filepath
    #         },
    #         "breakpoints": [{
    #             "line": bp_line
    #         }],
    #         "lines": [bp_line]
    #     }]

    #     with DebugClient(port=PORT, connecttimeout=CONNECT_TIMEOUT) as editor: # noqa
    #         adapter, session = editor.host_local_debugger(
    #             argv, env=env, cwd=cwd, timeout=CONNECT_TIMEOUT)

    #         terminated = session.get_awaiter_for_event('terminated')
    #         exited = session.get_awaiter_for_event('exited')
    #         thread_exit = session.get_awaiter_for_event(
    #             'thread',
    #             lambda msg: msg.body.get("reason", "") == "exited")  # noqa

    #         with session.wait_for_event("stopped") as result:
    #             (
    #                 req_initialize,
    #                 req_launch,
    #                 req_config,
    #                 reqs_bps,
    #                 _,
    #                 _,
    #             ) = lifecycle_handshake(
    #                 session, "launch", breakpoints=breakpoints)

    #         req_bps, = reqs_bps  # There should only be one.
    #         tid = result["msg"].body["threadId"]

    #         stacktrace = session.send_request("stackTrace", threadId=tid)
    #         with session.wait_for_event("continued"):
    #             cont = session.send_request("continue", threadId=tid)

    #         adapter.wait()
    #         Awaitable.wait_all(exited, terminated, stacktrace, exited,
    #                            thread_exit)  # noqa

    #     received = list(_strip_newline_output_events(session.received))

    #     # One for foo and one for bar, others for Python/ptvsd stuff.
    #     module_events = self.find_events(received, 'module')
    #     self.assertGreaterEqual(len(module_events), 2)

    #     self.assert_message_is_subset(
    #         module_events[0],
    #         self.new_event(
    #             "module",
    #             module={
    #                 "id": 1,
    #                 "name": "mymod.bar" if self.IS_MODULE else "bar",
    #             },
    #             reason="new",
    #         ))

    #     # TODO: Check for foo.

    #     self.assertGreaterEqual(stacktrace.resp.body["totalFrames"], 1)
    #     self.assert_message_is_subset(
    #         stacktrace.resp,
    #         self.new_response(
    #             stacktrace.req,
    #             **{
    #                 # We get Python and PTVSD frames as well.
    #                 # "totalFrames": 2,
    #                 "stackFrames": [
    #                     {
    #                         "id": 1,
    #                         "name": "do_something",
    #                         "source": {
    #                             # "path": bar_filepath,
    #                             "sourceReference": 0
    #                         },
    #                         "line": bp_line,
    #                         "column": 1,
    #                     },
    #                     {
    #                         "id": 2,
    #                         "name": "foo",
    #                         "source": {
    #                             # "path": filepath,
    #                             "sourceReference": 0
    #                         },
    #                         "line": foo_line,
    #                         "column": 1,
    #                     }
    #                 ],
    #             }))

    #     # Skipping the 'thread exited' and 'terminated' messages which
    #     # may appear randomly in the received list.
    #     self.assert_contains(
    #         received,
    #         [
    #             self.new_version_event(session.received),
    #             self.new_response(req_initialize.req, **INITIALIZE_RESPONSE),
    #             self.new_event("initialized"),
    #             self.new_response(req_launch.req),
    #             self.new_response(
    #                 req_bps.req, **{
    #                     "breakpoints": [{
    #                         "id": 1,
    #                         "line": bp_line,
    #                         "verified": True
    #                     }]
    #                 }),
    #             self.new_response(req_config.req),
    #             self.new_event(
    #                 "process", **{
    #                     "isLocalProcess": True,
    #                     "systemProcessId": adapter.pid,
    #                     "startMethod": "launch",
    #                     "name": expected_module,
    #                 }),
    #             self.new_event("thread", reason="started", threadId=tid),
    #             self.new_event(
    #                 "stopped",
    #                 reason="breakpoint",
    #                 threadId=tid,
    #                 text=None,
    #                 description=None,
    #             ),
    #             self.new_response(cont.req),
    #             self.new_event("continued", threadId=tid),
    #         ],
    #     )

    # def test_with_log_points(self):
    #     source = dedent("""
    #         print('foo')
    #         a = 1
    #         for i in range(2):
    #             # <Token>
    #             b = i
    #         print('bar')
    #         """)
    #     (filename, filepath, env, expected_module, argv,
    #      cwd) = self.get_test_info(source)
    #     bp_line = self.find_line(filepath, 'Token')
    #     breakpoints = [{
    #         "source": {
    #             "path": filepath,
    #             "name": filename
    #         },
    #         "breakpoints": [{
    #             "line": bp_line,
    #             "logMessage": "{a + i}"
    #         }],
    #         "lines": [bp_line]
    #     }]
    #     options = {"debugOptions": ["RedirectOutput"]}

    #     with DebugClient(port=PORT, connecttimeout=CONNECT_TIMEOUT) as editor: # noqa
    #         adapter, session = editor.host_local_debugger(
    #             argv, env=env, cwd=cwd, timeout=CONNECT_TIMEOUT)
    #         exited = session.get_awaiter_for_event('exited')
    #         thread_exit = session.get_awaiter_for_event(
    #             'thread',
    #             lambda msg: msg.body.get("reason", "") == "exited")  # noqa
    #         with session.wait_for_event("terminated"):
    #             (
    #                 req_initialize,
    #                 req_launch,
    #                 req_config,
    #                 reqs_bps,
    #                 _,
    #                 _,
    #             ) = lifecycle_handshake(
    #                 session,
    #                 "launch",
    #                 breakpoints=breakpoints,
    #                 options=options)
    #             req_bps, = reqs_bps  # There should only be one.

    #         adapter.wait()
    #         Awaitable.wait_all(exited, thread_exit)

    #     # Skipping the 'thread exited' and 'terminated' messages which
    #     # may appear randomly in the received list.
    #     received = list(_strip_newline_output_events(session.received))
    #     self.assert_contains(
    #         received,
    #         [
    #             self.new_version_event(session.received),
    #             self.new_response(req_initialize.req, **INITIALIZE_RESPONSE),
    #             self.new_event("initialized"),
    #             self.new_response(req_launch.req),
    #             self.new_response(
    #                 req_bps.req, **{
    #                     "breakpoints": [{
    #                         "id": 1,
    #                         "line": bp_line,
    #                         "verified": True
    #                     }]
    #                 }),
    #             self.new_response(req_config.req),
    #             self.new_event(
    #                 "process", **{
    #                     "isLocalProcess": True,
    #                     "systemProcessId": adapter.pid,
    #                     "startMethod": "launch",
    #                     "name": expected_module,
    #                 }),
    #             self.new_event("thread", reason="started", threadId=1),
    #             self.new_event("output", category="stdout", output="foo"),
    #             self.new_event(
    #                 "output", category="stdout",
    #                 output="1" + os.linesep),  # noqa
    #             self.new_event(
    #                 "output", category="stdout",
    #                 output="2" + os.linesep),  # noqa
    #             self.new_event("output", category="stdout", output="bar"),
    #         ],
    #     )

    # def test_with_conditional_break_points(self):
    #     source = dedent("""
    #         a = 1
    #         b = 2
    #         for i in range(5):
    #             # <Token>
    #             print(i)
    #         """)
    #     (filename, filepath, env, expected_module, argv,
    #      cwd) = self.get_test_info(source)
    #     bp_line = self.find_line(filepath, 'Token')
    #     breakpoints = [{
    #         "source": {
    #             "path": filepath,
    #             "name": filename
    #         },
    #         "breakpoints": [{
    #             "line": bp_line,
    #             "condition": "i == 2"
    #         }],
    #         "lines": [bp_line]
    #     }]
    #     options = {"debugOptions": ["RedirectOutput"]}

    #     with DebugClient(port=PORT, connecttimeout=CONNECT_TIMEOUT) as editor: # noqa
    #         adapter, session = editor.host_local_debugger(
    #             argv, env=env, cwd=cwd, timeout=CONNECT_TIMEOUT)

    #         exited = session.get_awaiter_for_event('exited')
    #         terminated = session.get_awaiter_for_event('terminated')
    #         thread_exit = session.get_awaiter_for_event(
    #             'thread',
    #             lambda msg: msg.body.get("reason", "") == "exited")  # noqa

    #         with session.wait_for_event("stopped") as result:
    #             (
    #                 req_initialize,
    #                 req_launch,
    #                 req_config,
    #                 reqs_bps,
    #                 _,
    #                 _,
    #             ) = lifecycle_handshake(
    #                 session,
    #                 "launch",
    #                 breakpoints=breakpoints,
    #                 options=options)
    #         req_bps, = reqs_bps  # There should only be one.
    #         tid = result["msg"].body["threadId"]

    #         stacktrace = session.send_request(
    #             "stackTrace", threadId=tid, wait=True)  # noqa

    #         with session.wait_for_event("continued"):
    #             cont = session.send_request("continue", threadId=tid)

    #         adapter.wait()
    #         Awaitable.wait_all(terminated, exited, thread_exit)

    #     received = list(_strip_newline_output_events(session.received))

    #     self.assertGreaterEqual(stacktrace.resp.body["totalFrames"], 1)
    #     self.assert_message_is_subset(
    #         stacktrace.resp,
    #         self.new_response(
    #             stacktrace.req, **{
    #                 "stackFrames": [{
    #                     "id": 1,
    #                     "name": "<module>",
    #                     "source": {
    #                         "path": filepath,
    #                         "sourceReference": 0
    #                     },
    #                     "line": bp_line,
    #                     "column": 1,
    #                 }],
    #             }))

    #     # Skipping the 'thread exited' and 'terminated' messages which
    #     # may appear randomly in the received list.
    #     self.assert_contains(
    #         received,
    #         [
    #             self.new_version_event(session.received),
    #             self.new_response(req_initialize.req, **INITIALIZE_RESPONSE),
    #             self.new_event("initialized"),
    #             self.new_response(req_launch.req),
    #             self.new_response(
    #                 req_bps.req, **{
    #                     "breakpoints": [{
    #                         "id": 1,
    #                         "line": bp_line,
    #                         "verified": True
    #                     }]
    #                 }),
    #             self.new_response(req_config.req),
    #             self.new_event(
    #                 "process", **{
    #                     "isLocalProcess": True,
    #                     "systemProcessId": adapter.pid,
    #                     "startMethod": "launch",
    #                     "name": expected_module,
    #                 }),
    #             self.new_event("thread", reason="started", threadId=tid),
    #             self.new_event("output", category="stdout", output="0"),
    #             self.new_event("output", category="stdout", output="1"),
    #             self.new_event(
    #                 "stopped",
    #                 reason="breakpoint",
    #                 threadId=tid,
    #                 text=None,
    #                 description=None,
    #             ),
    #             self.new_response(cont.req),
    #             self.new_event("continued", threadId=tid),
    #             self.new_event("output", category="stdout", output="2"),
    #             self.new_event("output", category="stdout", output="3"),
    #             self.new_event("output", category="stdout", output="4"),
    #         ],
    #     )

    # @unittest.skip('To be fixed in #530')
    # def test_terminating_program(self):
    #     source = dedent("""
    #         import time

    #         while True:
    #             time.sleep(0.1)
    #         """)
    #     (filename, filepath, env, expected_module, argv,
    #      module_name) = self.get_test_info(source)

    #     with DebugClient(port=PORT, connecttimeout=CONNECT_TIMEOUT) as editor: # noqa
    #         adapter, session = editor.host_local_debugger(argv)

    #         exited = session.get_awaiter_for_event('exited')
    #         terminated = session.get_awaiter_for_event('terminated')

    #         (req_initialize, req_launch, req_config, _, _,
    #          _) = lifecycle_handshake(  # noqa
    #              session, "launch")

    #         Awaitable.wait_all(req_launch,
    #                            session.get_awaiter_for_event('thread'))  # noqa
    #         disconnect = session.send_request("disconnect")

    #         Awaitable.wait_all(exited, terminated, disconnect)
    #         adapter.wait()


class LaunchModuleLifecycleTests(LaunchLifecycleTests):
    def test_with_break_points(self):
        module_name = 'mymod_launch1'
        cwd = os.path.join(TEST_FILES_DIR)
        env = {"PYTHONPATH": cwd}
        bp_filename = os.path.join(cwd, module_name, '__init__.py')
        self.run_test_with_break_points(
            DebugInfo(modulename=module_name, env=env, cwd=cwd),
            bp_filename,
            bp_line=3)


class ServerAttachLifecycleTests(LaunchLifecycleTests):
    def test_with_break_points(self):
        filename = os.path.join(TEST_FILES_DIR, 'output.py')
        cwd = os.path.dirname(filename)
        argv = ['localhost', str(PORT)]
        self.run_test_with_break_points(
            DebugInfo(
                filename=filename, cwd=cwd, starttype='attach', argv=argv),
            filename,
            bp_line=3)


class PTVSDAttachLifecycleTests(LaunchLifecycleTests):
    def test_with_break_points(self):
        filename = os.path.join(TEST_FILES_DIR,
                                'attach_output.py')
        cwd = os.path.dirname(filename)
        argv = ['localhost', str(PORT)]
        self.run_test_with_break_points(
            DebugInfo(
                filename=filename,
                attachtype='import',
                cwd=cwd,
                starttype='attach',
                argv=argv),
            filename,
            bp_line=6)


class ServerAttachModuleLifecycleTests(LaunchLifecycleTests):  # noqa
    def test_with_break_points(self):
        module_name = 'mymod_launch1'
        cwd = os.path.join(TEST_FILES_DIR)
        env = {"PYTHONPATH": cwd}
        argv = ['localhost', str(PORT)]
        bp_filename = os.path.join(cwd, module_name, '__init__.py')
        self.run_test_with_break_points(
            DebugInfo(
                modulename=module_name,
                env=env,
                cwd=cwd,
                argv=argv,
                starttype='attach'),
            bp_filename,
            bp_line=3)


@unittest.skip('Needs fixing')
class PTVSDAttachModuleLifecycleTests(LaunchLifecycleTests):  # noqa
    def test_with_break_points(self):
        module_name = 'mymod_attach1'
        cwd = os.path.join(TEST_FILES_DIR)
        env = {"PYTHONPATH": cwd}
        argv = ['localhost', str(PORT)]
        bp_filename = os.path.join(cwd, module_name, '__init__.py')
        self.run_test_with_break_points(
            DebugInfo(
                modulename=module_name,
                env=env,
                cwd=cwd,
                argv=argv,
                attachtype='import',
                starttype='attach'),
            bp_filename,
            bp_line=6)
