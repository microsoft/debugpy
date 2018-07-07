import os
import os.path
import unittest

from ptvsd.wrapper import INITIALIZE_RESPONSE  # noqa

from . import (_strip_newline_output_events, lifecycle_handshake,
               LifecycleTestsBase, DebugInfo, ROOT, PORT)

TEST_FILES_DIR = os.path.join(ROOT, 'tests', 'resources', 'system_tests',
                              'test_breakpoints')


class BreakpointTests(LifecycleTestsBase):
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

    def run_test_with_break_points_across_files(
            self, debug_info, first_file, second_file, second_file_line,
            expected_modules, expected_stacktrace):
        breakpoints = [{
            "source": {
                "path": second_file
            },
            "breakpoints": [{
                "line": second_file_line
            }]
        }]

        with self.start_debugging(debug_info) as dbg:
            session = dbg.session
            with session.wait_for_event("stopped") as result:
                (
                    _,
                    req_launch_attach,
                    _,
                    _,
                    _,
                    _,
                ) = lifecycle_handshake(
                    session, debug_info.starttype, breakpoints=breakpoints)

                req_launch_attach.wait()

            tid = result["msg"].body["threadId"]
            stacktrace = session.send_request("stackTrace", threadId=tid)
            stacktrace.wait()
            session.send_request("continue", threadId=tid)

        received = list(_strip_newline_output_events(session.received))

        for mod in expected_modules:
            found_mod = self.find_events(received, 'module', mod)
            self.assertEqual(
                len(found_mod), 1, 'Modul not found {}'.format(mod))

        self.assert_is_subset(stacktrace.resp, expected_stacktrace)

    def run_test_conditional_break_points(self, debug_info):
        breakpoints = [{
            "source": {
                "path": debug_info.filename
            },
            "breakpoints": [{
                "line": 4,
                "condition": "i == 2"
            }],
            "lines": [4]
        }]

        with self.start_debugging(debug_info) as dbg:
            session = dbg.session
            with session.wait_for_event("stopped") as result:
                (
                    _,
                    _,
                    _,
                    _,
                    _,
                    _,
                ) = lifecycle_handshake(
                    session, debug_info.starttype, breakpoints=breakpoints)

            tid = result["msg"].body["threadId"]
            stacktrace = session.send_request("stackTrace", threadId=tid)
            stacktrace.wait()

            frame_id = stacktrace.resp.body["stackFrames"][0]["id"]
            scopes = session.send_request('scopes', frameId=frame_id)
            scopes.wait()
            variables_reference = scopes.resp.body["scopes"][0][
                "variablesReference"]
            variables = session.send_request(
                'variables', variablesReference=variables_reference)
            variables.wait()
            session.send_request("continue", threadId=tid)

        self.assert_is_subset(variables.resp.body["variables"],
                              [{
                                  "name": "a",
                                  "type": "int",
                                  "value": "1",
                                  "evaluateName": "a"
                              }, {
                                  "name": "b",
                                  "type": "int",
                                  "value": "2",
                                  "evaluateName": "b"
                              }, {
                                  "name": "c",
                                  "type": "int",
                                  "value": "1",
                                  "evaluateName": "c"
                              }, {
                                  "name": "i",
                                  "type": "int",
                                  "value": "2",
                                  "evaluateName": "i"
                              }])

    def run_test_hit_conditional_break_points(self, debug_info, **kwargs):
        breakpoints = [{
            "source": {
                "path": debug_info.filename
            },
            "breakpoints": [{
                "line": 4,
                "hitCondition": kwargs['hit_condition']
            }],
            "lines": [4]
        }]

        i_values = []
        with self.start_debugging(debug_info) as dbg:
            session = dbg.session
            hits = kwargs['hits']
            count = 0
            while count < hits:
                if count == 0:
                    with session.wait_for_event("stopped") as result:
                        (
                            _,
                            _,
                            _,
                            _,
                            _,
                            _,
                        ) = lifecycle_handshake(
                            session, debug_info.starttype,
                            breakpoints=breakpoints)

                tid = result["msg"].body["threadId"]
                stacktrace = session.send_request("stackTrace", threadId=tid)
                stacktrace.wait()

                frame_id = stacktrace.resp.body["stackFrames"][0]["id"]
                scopes = session.send_request('scopes', frameId=frame_id)
                scopes.wait()
                variables_reference = scopes.resp.body["scopes"][0][
                    "variablesReference"]
                variables = session.send_request(
                    'variables', variablesReference=variables_reference)
                variables.wait()
                i_value = list(int(v['value'])
                               for v in variables.resp.body["variables"]
                               if v['name'] == 'i')
                i_values.append(i_value[0] if len(i_value) > 0 else None)
                count = count + 1
                if count < hits:
                    with session.wait_for_event("stopped") as result:
                        session.send_request("continue", threadId=tid)
                else:
                    session.send_request("continue", threadId=tid)
        self.assertEqual(i_values, kwargs['expected'])

    def run_test_logpoints(self, debug_info):
        options = {"debugOptions": ["RedirectOutput"]}
        breakpoints = [{
            "source": {
                "path": debug_info.filename
            },
            "breakpoints": [{
                "line": 4,
                "logMessage": "Sum of a + i = {a + i}"
            }],
            "lines": [4]
        }]

        with self.start_debugging(debug_info) as dbg:
            session = dbg.session
            (
                _,
                _,
                _,
                _,
                _,
                _,
            ) = lifecycle_handshake(
                session,
                debug_info.starttype,
                options=options,
                breakpoints=breakpoints)

        received = list(_strip_newline_output_events(session.received))
        expected_events = [
            self.new_event(
                "output",
                category="stdout",
                output="Sum of a + i = {}{}".format(i + 1, os.linesep))
            for i in range(5)
        ]

        self.assert_contains(received, expected_events)


class LaunchFileTests(BreakpointTests):
    def test_with_break_points(self):
        filename = os.path.join(TEST_FILES_DIR, 'output.py')
        cwd = os.path.dirname(filename)
        self.run_test_with_break_points(
            DebugInfo(filename=filename, cwd=cwd), filename, bp_line=3)

    def test_with_break_points_across_files(self):
        first_file = os.path.join(TEST_FILES_DIR, 'foo.py')
        second_file = os.path.join(TEST_FILES_DIR, 'bar.py')
        cwd = os.path.dirname(first_file)
        expected_modules = [{
            "reason": "new",
            "module": {
                "path": second_file,
                "name": "bar"
            }
        }, {
            "reason": "new",
            "module": {
                "path": first_file,
                "name": "__main__"
            }
        }]
        expected_stacktrace = {
            "stackFrames": [{
                "name": "do_bar",
                "source": {
                    "path": second_file,
                    "sourceReference": 0
                },
                "line": 2,
                "column": 1
            }, {
                "name": "do_foo",
                "source": {
                    "path": first_file,
                    "sourceReference": 0
                },
                "line": 5,
                "column": 1
            }, {
                "id": 3,
                "name": "<module>",
                "source": {
                    "path": first_file,
                    "sourceReference": 0
                },
                "line": 8,
                "column": 1
            }],
        }
        self.run_test_with_break_points_across_files(
            DebugInfo(filename=first_file, cwd=cwd), first_file, second_file,
            2, expected_modules, expected_stacktrace)

    def test_conditional_break_points(self):
        filename = os.path.join(TEST_FILES_DIR, 'loopy.py')
        cwd = os.path.dirname(filename)
        self.run_test_conditional_break_points(
            DebugInfo(filename=filename, cwd=cwd))

    def test_logpoints(self):
        filename = os.path.join(TEST_FILES_DIR, 'loopy.py')
        cwd = os.path.dirname(filename)
        self.run_test_logpoints(DebugInfo(filename=filename, cwd=cwd))

    def test_hit_conditional_break_points_equal(self):
        filename = os.path.join(TEST_FILES_DIR, 'loopy.py')
        cwd = os.path.dirname(filename)
        self.run_test_hit_conditional_break_points(
            DebugInfo(filename=filename, cwd=cwd),
            hit_condition='== 5',
            hits=1,
            expected=[4])

    def test_hit_conditional_break_points_equal2(self):
        filename = os.path.join(TEST_FILES_DIR, 'loopy.py')
        cwd = os.path.dirname(filename)
        self.run_test_hit_conditional_break_points(
            DebugInfo(filename=filename, cwd=cwd),
            hit_condition='5',
            hits=1,
            expected=[4])

    def test_hit_conditional_break_points_greater(self):
        filename = os.path.join(TEST_FILES_DIR, 'loopy.py')
        cwd = os.path.dirname(filename)
        self.run_test_hit_conditional_break_points(
            DebugInfo(filename=filename, cwd=cwd),
            hit_condition='> 5',
            hits=5,
            expected=[5, 6, 7, 8, 9])

    def test_hit_conditional_break_points_greater_or_equal(self):
        filename = os.path.join(TEST_FILES_DIR, 'loopy.py')
        cwd = os.path.dirname(filename)
        self.run_test_hit_conditional_break_points(
            DebugInfo(filename=filename, cwd=cwd),
            hit_condition='>= 5',
            hits=6,
            expected=[4, 5, 6, 7, 8, 9])

    def test_hit_conditional_break_points_lesser(self):
        filename = os.path.join(TEST_FILES_DIR, 'loopy.py')
        cwd = os.path.dirname(filename)
        self.run_test_hit_conditional_break_points(
            DebugInfo(filename=filename, cwd=cwd),
            hit_condition='< 5',
            hits=4,
            expected=[0, 1, 2, 3])

    def test_hit_conditional_break_points_lesser_or_equal(self):
        filename = os.path.join(TEST_FILES_DIR, 'loopy.py')
        cwd = os.path.dirname(filename)
        self.run_test_hit_conditional_break_points(
            DebugInfo(filename=filename, cwd=cwd),
            hit_condition='<= 5',
            hits=5,
            expected=[0, 1, 2, 3, 4])

    def test_hit_conditional_break_points_mod(self):
        filename = os.path.join(TEST_FILES_DIR, 'loopy.py')
        cwd = os.path.dirname(filename)
        self.run_test_hit_conditional_break_points(
            DebugInfo(filename=filename, cwd=cwd),
            hit_condition='% 4',
            hits=2,
            expected=[3, 7])


class LaunchModuleTests(BreakpointTests):
    def test_with_break_points(self):
        module_name = 'mymod_launch1'
        cwd = os.path.join(TEST_FILES_DIR)
        env = {"PYTHONPATH": cwd}
        bp_filename = os.path.join(cwd, module_name, '__init__.py')
        self.run_test_with_break_points(
            DebugInfo(modulename=module_name, env=env, cwd=cwd),
            bp_filename,
            bp_line=3)

    def test_with_break_points_across_files(self):
        module_name = 'mymod_foo'
        first_file = os.path.join(TEST_FILES_DIR, module_name, '__init__.py')
        second_file = os.path.join(TEST_FILES_DIR, 'mymod_bar', 'bar.py')
        cwd = os.path.join(TEST_FILES_DIR)
        env = {"PYTHONPATH": cwd}
        expected_modules = [{
            "reason": "new",
            "module": {
                "package": "mymod_bar",
                "path": second_file,
                "name": "mymod_bar.bar"
            }
        }, {
            "reason": "new",
            "module": {
                "path": first_file,
                "name": "__main__"
            }
        }]
        expected_stacktrace = {
            "stackFrames": [{
                "name": "do_bar",
                "source": {
                    "path": second_file,
                    "sourceReference": 0
                },
                "line": 2,
                "column": 1
            }, {
                "name": "do_foo",
                "source": {
                    "path": first_file,
                    "sourceReference": 0
                },
                "line": 5,
                "column": 1
            }, {
                "id": 3,
                "name": "<module>",
                "source": {
                    "path": first_file,
                    "sourceReference": 0
                },
                "line": 8,
                "column": 1
            }],
        }
        self.run_test_with_break_points_across_files(
            DebugInfo(modulename=module_name, cwd=cwd, env=env), first_file,
            second_file, 2, expected_modules, expected_stacktrace)


class ServerAttachTests(BreakpointTests):
    def test_with_break_points(self):
        filename = os.path.join(TEST_FILES_DIR, 'output.py')
        cwd = os.path.dirname(filename)
        argv = ['localhost', str(PORT)]
        self.run_test_with_break_points(
            DebugInfo(
                filename=filename, cwd=cwd, starttype='attach', argv=argv),
            filename,
            bp_line=3)


class PTVSDAttachTests(BreakpointTests):
    def test_with_break_points(self):
        filename = os.path.join(TEST_FILES_DIR, 'attach_output.py')
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


class ServerAttachModuleTests(BreakpointTests):  # noqa
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
class PTVSDAttachModuleTests(BreakpointTests):  # noqa
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
