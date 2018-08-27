import os
import os.path
import time
from tests.helpers.resource import TestResources
from . import (
    _strip_newline_output_events, lifecycle_handshake,
    LifecycleTestsBase, DebugInfo
)

TEST_FILES = TestResources.from_module(__name__)


class NoOutputTests(LifecycleTestsBase):
    def run_test_with_no_output(self, debug_info):
        options = {'debugOptions': ['RedirectOutput']}
        with self.start_debugging(debug_info) as dbg:
            session = dbg.session
            lifecycle_handshake(session, debug_info.starttype,
                                options=options)
        out = dbg.adapter._proc.output.decode('utf-8')
        self.assertEqual(out, '')

    def test_with_no_output(self):
        filename = TEST_FILES.resolve('nooutput.py')
        cwd = os.path.dirname(filename)
        self.run_test_with_no_output(
            DebugInfo(filename=filename, cwd=cwd))


class ThreadCountTests(LifecycleTestsBase):
    def run_test_threads(self, debug_info, bp_filename, bp_line, count):
        breakpoints = [{
            'source': {
                'path': bp_filename
            },
            'breakpoints': [{
                'line': bp_line
            }]
        }]
        with self.start_debugging(debug_info) as dbg:
            session = dbg.session
            with session.wait_for_event('stopped') as result:
                lifecycle_handshake(
                                    session, debug_info.starttype,
                                    breakpoints=breakpoints,
                                    threads=True)
            # Give extra time for thread state to be captured
            time.sleep(1)
            event = result['msg']
            tid = event.body['threadId']
            req_threads = session.send_request('threads')
            req_threads.wait()
            threads = req_threads.resp.body['threads']

            session.send_request('continue', threadId=tid)

        self.assertEqual(count, len(threads))

    def test_single_thread(self):
        filename = TEST_FILES.resolve('single_thread.py')
        cwd = os.path.dirname(filename)
        self.run_test_threads(
            DebugInfo(filename=filename, cwd=cwd),
            bp_filename=filename, bp_line=2, count=1)

    def test_multi_thread(self):
        filename = TEST_FILES.resolve('three_threads.py')
        cwd = os.path.dirname(filename)
        self.run_test_threads(
            DebugInfo(filename=filename, cwd=cwd),
            bp_filename=filename, bp_line=22, count=3)


class StopOnEntryTests(LifecycleTestsBase):
    def run_test_stop_on_entry_enabled(self, debug_info, expected_source_path):
        options = {'debugOptions': ['RedirectOutput', 'StopOnEntry']}
        with self.start_debugging(debug_info) as dbg:
            session = dbg.session
            with session.wait_for_event('stopped') as result:
                lifecycle_handshake(
                                    session, debug_info.starttype,
                                    options=options)
            received_before = self.find_events(session.received, 'output')

            event = result['msg']
            tid = event.body['threadId']

            req_stacktrace = session.send_request(
                'stackTrace',
                threadId=tid,
            )
            req_stacktrace.wait()
            stacktrace = req_stacktrace.resp.body

            session.send_request('continue', threadId=tid)

        # We should be broken in on the first line:
        self.assertGreaterEqual(stacktrace['totalFrames'], 1)
        self.assert_is_subset(stacktrace, {
            'stackFrames': [{
                'id': 1,
                'name': '<module>',
                'source': {
                    'path': expected_source_path,
                    'sourceReference': 0,
                },
                'line': 1,
                'column': 1,
            }],
        })

        # Make sure there is no stdout based output event
        for e in received_before:
            self.assertFalse(e.body['category'] == 'stdout')

        received = list(_strip_newline_output_events(session.received))
        self.assert_contains(received, [
            self.new_event('continued', threadId=tid),
            self.new_event('output', category='stdout', output='one'),
            self.new_event('output', category='stdout', output='two'),
            self.new_event('output', category='stdout', output='three'),
            self.new_event('exited', exitCode=0),
            self.new_event('terminated'),
        ])

    def run_test_stop_on_entry_disabled(self, debug_info):
        options = {'debugOptions': ['RedirectOutput']}
        with self.start_debugging(debug_info) as dbg:
            session = dbg.session
            lifecycle_handshake(
                                session, debug_info.starttype,
                                options=options)

        received = list(_strip_newline_output_events(session.received))
        self.assert_contains(received, [
            self.new_event('output', category='stdout', output='one'),
            self.new_event('output', category='stdout', output='two'),
            self.new_event('output', category='stdout', output='three'),
            self.new_event('exited', exitCode=0),
            self.new_event('terminated'),
        ])


class StopOnEntryLaunchFileTests(StopOnEntryTests):
    def test_stop_on_entry_enabled(self):
        filename = TEST_FILES.resolve('stoponentry.py')
        cwd = os.path.dirname(filename)
        self.run_test_stop_on_entry_enabled(
            DebugInfo(filename=filename, cwd=cwd),
            filename)

    def test_stop_on_entry_disabled(self):
        filename = TEST_FILES.resolve('stoponentry.py')
        cwd = os.path.dirname(filename)
        self.run_test_stop_on_entry_disabled(
            DebugInfo(filename=filename, cwd=cwd))


class StopOnEntryLaunchModuleTests(StopOnEntryTests):
    def test_stop_on_entry_enabled(self):
        filename = TEST_FILES.resolve('stoponentry.py')
        env = TEST_FILES.env_with_py_path()
        cwd = TEST_FILES.root
        self.run_test_stop_on_entry_enabled(
            DebugInfo(
                modulename='stoponentry',
                cwd=cwd,
                env=env),
            filename)

    def test_stop_on_entry_disabled(self):
        env = TEST_FILES.env_with_py_path()
        cwd = TEST_FILES.root
        self.run_test_stop_on_entry_disabled(
            DebugInfo(
                modulename='stoponentry',
                cwd=cwd,
                env=env))


class StopOnEntryLaunchPackageTests(StopOnEntryTests):
    def test_stop_on_entry_enabled(self):
        filename = TEST_FILES.resolve('mymod', '__init__.py')
        env = TEST_FILES.env_with_py_path()
        cwd = TEST_FILES.root
        self.run_test_stop_on_entry_enabled(
            DebugInfo(
                modulename='mymod',
                cwd=cwd,
                env=env),
            filename)

    def test_stop_on_entry_disabled(self):
        env = TEST_FILES.env_with_py_path()
        cwd = TEST_FILES.root
        self.run_test_stop_on_entry_disabled(
            DebugInfo(
                modulename='mymod',
                cwd=cwd,
                env=env))


class ShowReturnValueTests(LifecycleTestsBase):
    def _debugger_step_next(self, session, thread_id):
        stopped = session.get_awaiter_for_event('stopped')
        req_next = session.send_request('next', threadId=thread_id)
        req_next.wait(timeout=2.0)
        stopped.wait(timeout=2.0)

    def _get_variables(self, session, thread_id):
        req_stacktrace = session.send_request(
            'stackTrace',
            threadId=thread_id,
        )
        req_stacktrace.wait(timeout=2.0)

        frames = req_stacktrace.resp.body['stackFrames']
        frame_id = frames[0]['id']

        req_scopes = session.send_request(
            'scopes',
            frameId=frame_id,
        )
        req_scopes.wait(timeout=2.0)

        scopes = req_scopes.resp.body['scopes']
        variables_reference = scopes[0]['variablesReference']

        req_variables = session.send_request(
            'variables',
            variablesReference=variables_reference,
        )
        req_variables.wait(timeout=2.0)

        return req_variables.resp.body['variables']

    def run_test_return_values(self, debug_info, is_enabled):
        if is_enabled:
            options = {'debugOptions': ['RedirectOutput', 'ShowReturnValue']}
        else:
            options = {'debugOptions': ['RedirectOutput']}

        breakpoints = [{
            'source': {
                'path': debug_info.filename
            },
            'breakpoints': [{'line': 10}, {'line': 11}, {'line': 12}],
            'lines': [10, 11, 12]
        }]
        with self.start_debugging(debug_info) as dbg:
            session = dbg.session
            stopped = session.get_awaiter_for_event('stopped')
            (_, req_launch_attach, _, _, _, _
             ) = lifecycle_handshake(session, debug_info.starttype,
                                     options=options,
                                     breakpoints=breakpoints)
            req_launch_attach.wait(timeout=3.0)

            stopped.wait()
            thread_id = stopped.event.body['threadId']

            self._debugger_step_next(session, thread_id)
            variables = self._get_variables(session, thread_id)

            return_values = list(v for v in variables
                                 if v['name'].startswith('(return) '))

            if is_enabled:
                self.assertEqual(len(return_values), 1)
                self.assertEqual(return_values[0]['name'],
                                 '(return) MyClass.do_something')
                self.assertEqual(return_values[0]['value'],
                                 "'did something'")
                self.assertEqual(return_values[0]['type'],
                                 'str')
                attributes = return_values[0]['presentationHint']['attributes']
                self.assertTrue('readOnly' in attributes)
            else:
                self.assertEqual(len(return_values), 0)

            self._debugger_step_next(session, thread_id)
            variables = self._get_variables(session, thread_id)

            return_values = list(v for v in variables
                                 if v['name'].startswith('(return) '))

            if is_enabled:
                self.assertEqual(len(return_values), 2)
                self.assertEqual(return_values[0]['name'],
                                 '(return) MyClass.do_something')
                self.assertEqual(return_values[0]['value'],
                                 "'did something'")
                self.assertEqual(return_values[0]['type'],
                                 'str')
                attributes = return_values[0]['presentationHint']['attributes']
                self.assertTrue('readOnly' in attributes)

                self.assertEqual(return_values[1]['name'],
                                 '(return) my_func')
                self.assertEqual(return_values[1]['value'],
                                 "'did more things'")
                self.assertEqual(return_values[1]['type'],
                                 'str')
                attributes = return_values[1]['presentationHint']['attributes']
                self.assertTrue('readOnly' in attributes)
            else:
                self.assertEqual(len(return_values), 0)

            exited = session.get_awaiter_for_event('exited')
            session.send_request('continue').wait(timeout=2.0)
            exited.wait(timeout=3.0)

    def test_return_values_enabled(self):
        filename = TEST_FILES.resolve('returnvalues.py')
        cwd = os.path.dirname(filename)
        self.run_test_return_values(
            DebugInfo(filename=filename, cwd=cwd),
            is_enabled=True)

    def test_return_values_disabled(self):
        filename = TEST_FILES.resolve('returnvalues.py')
        cwd = os.path.dirname(filename)
        self.run_test_return_values(
            DebugInfo(filename=filename, cwd=cwd),
            is_enabled=False)
