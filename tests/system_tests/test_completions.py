import os
import os.path

from tests.helpers.resource import TestResources
from . import (
    lifecycle_handshake, LifecycleTestsBase, DebugInfo, PORT,
)


TEST_FILES = TestResources.from_module(__name__)


class CompletionsTests(LifecycleTestsBase):

    def run_test_completions(self, debug_info, bp_filename, bp_line, expected):
        pathMappings = []
        # Required to ensure sourceReference = 0
        if (debug_info.starttype == 'attach'):
            pathMappings.append({
                'localRoot': debug_info.cwd,
                'remoteRoot': debug_info.cwd
            })
        options = {
            'debugOptions': ['RedirectOutput'],
            'pathMappings': pathMappings
        }
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
                (_, req_launch_attach, _, _, _, _,
                 ) = lifecycle_handshake(session, debug_info.starttype,
                                         options=options,
                                         breakpoints=breakpoints)
                req_launch_attach.wait()

            event = result['msg']
            tid = event.body['threadId']

            req_stacktrace = session.send_request(
                'stackTrace',
                threadId=tid,
            )
            req_stacktrace.wait()
            frames = req_stacktrace.resp.body['stackFrames']
            frame_id = frames[0]['id']

            req_completions = session.send_request(
                'completions',
                text='some',
                frameId=int(frame_id),
                column=1
            )
            req_completions.wait(timeout=2.0)
            targets = req_completions.resp.body['targets']

            # make a request with bad frame id
            bad_req_completions = session.send_request(
                'completions',
                text='some',
                frameId=int(1234),
                column=1
            )
            bad_req_completions.wait(timeout=2.0)
            bad_result = bad_req_completions.resp.success

            session.send_request(
                'continue',
                threadId=tid,
            )

        targets.sort(key=lambda t: t['label'])
        expected.sort(key=lambda t: t['label'])
        self.assertEqual(targets, expected)
        self.assertEqual(bad_result, False)

    def run_test_outermost_scope(self, debug_info, filename, line):
        self.run_test_completions(
            debug_info,
            bp_filename=filename,
            bp_line=line,
            expected=[
                {
                    'label': 'SomeClass',
                    'type': 'class'
                },
                {
                    'label': 'someFunction',
                    'type': 'function'
                }
            ]
        )

    def run_test_in_function(self, debug_info, filename, line):
        self.run_test_completions(
            debug_info,
            bp_filename=filename,
            bp_line=line,
            expected=[
                {
                    'label': 'SomeClass',
                    'type': 'class'
                },
                {
                    'label': 'someFunction',
                    'type': 'function'
                },
                {
                    'label': 'someVar',
                    'type': 'field'
                },
                {
                    'label': 'someVariable',
                    'type': 'field'
                }
            ]
        )

    def run_test_in_method(self, debug_info, filename, line):
        self.run_test_completions(
            debug_info,
            bp_filename=filename,
            bp_line=line,
            expected=[
                {
                    'label': 'SomeClass',
                    'type': 'class'
                },
                {
                    'label': 'someFunction',
                    'type': 'function'
                },
                {
                    'label': 'someVariable',
                    'type': 'field'
                }
            ]
        )


class LaunchFileTests(CompletionsTests):
    def _get_debug_info(self):
        filename = TEST_FILES.resolve('launch_completions.py')
        cwd = os.path.dirname(filename)
        return DebugInfo(filename=filename, cwd=cwd)

    def test_outermost_scope(self):
        debug_info = self._get_debug_info()
        self.run_test_outermost_scope(debug_info, debug_info.filename, 16)

    def test_in_function(self):
        debug_info = self._get_debug_info()
        self.run_test_in_function(debug_info, debug_info.filename, 12)

    def test_in_method(self):
        debug_info = self._get_debug_info()
        self.run_test_in_method(debug_info, debug_info.filename, 7)


class LaunchModuleTests(CompletionsTests):
    def _get_debug_info(self):
        module_name = 'launch_completions'
        filename = TEST_FILES.resolve('launch_completions.py')
        env = TEST_FILES.env_with_py_path()
        cwd = TEST_FILES.root
        return DebugInfo(modulename=module_name, cwd=cwd, env=env), filename

    def test_outermost_scope(self):
        debug_info, filename = self._get_debug_info()
        self.run_test_outermost_scope(debug_info, filename, 16)

    def test_in_function(self):
        debug_info, filename = self._get_debug_info()
        self.run_test_in_function(debug_info, filename, 12)

    def test_in_method(self):
        debug_info, filename = self._get_debug_info()
        self.run_test_in_method(debug_info, filename, 7)


class ServerAttachTests(CompletionsTests):
    def _get_debug_info(self):
        filename = TEST_FILES.resolve('launch_completions.py')
        cwd = os.path.dirname(filename)
        argv = ['localhost', str(PORT)]
        return DebugInfo(
                filename=filename,
                cwd=cwd,
                starttype='attach',
                argv=argv,
            ), filename

    def test_outermost_scope(self):
        debug_info, filename = self._get_debug_info()
        self.run_test_outermost_scope(debug_info, filename, 16)

    def test_in_function(self):
        debug_info, filename = self._get_debug_info()
        self.run_test_in_function(debug_info, filename, 12)

    def test_in_method(self):
        debug_info, filename = self._get_debug_info()
        self.run_test_in_method(debug_info, filename, 7)


class ServerAttachModuleTests(CompletionsTests):
    def _get_debug_info(self):
        module_name = 'launch_completions'
        filename = TEST_FILES.resolve('launch_completions.py')
        env = TEST_FILES.env_with_py_path()
        cwd = TEST_FILES.root
        argv = ['localhost', str(PORT)]
        return DebugInfo(
                modulename=module_name,
                env=env,
                cwd=cwd,
                argv=argv,
                starttype='attach',
            ), filename

    def test_outermost_scope(self):
        debug_info, filename = self._get_debug_info()
        self.run_test_outermost_scope(debug_info, filename, 16)

    def test_in_function(self):
        debug_info, filename = self._get_debug_info()
        self.run_test_in_function(debug_info, filename, 12)

    def test_in_method(self):
        debug_info, filename = self._get_debug_info()
        self.run_test_in_method(debug_info, filename, 7)


class PTVSDAttachTests(CompletionsTests):
    def _get_debug_info(self):
        filename = TEST_FILES.resolve('attach_completions.py')
        cwd = os.path.dirname(filename)
        argv = ['localhost', str(PORT)]
        return DebugInfo(
                filename=filename,
                attachtype='import',
                cwd=cwd,
                starttype='attach',
                argv=argv,
            ), filename

    def test_outermost_scope(self):
        debug_info, filename = self._get_debug_info()
        self.run_test_outermost_scope(debug_info, filename, 23)

    def test_in_function(self):
        debug_info, filename = self._get_debug_info()
        self.run_test_in_function(debug_info, filename, 19)

    def test_in_method(self):
        debug_info, filename = self._get_debug_info()
        self.run_test_in_method(debug_info, filename, 14)


class PTVSDAttachModuleTests(CompletionsTests):
    def _get_debug_info(self):
        filename = TEST_FILES.resolve('attach_completions.py')
        module_name = 'attach_completions'
        env = TEST_FILES.env_with_py_path()
        cwd = TEST_FILES.root
        argv = ['localhost', str(PORT)]
        return DebugInfo(
                modulename=module_name,
                env=env,
                cwd=cwd,
                argv=argv,
                attachtype='import',
                starttype='attach',
            ), filename

    def test_outermost_scope(self):
        debug_info, filename = self._get_debug_info()
        self.run_test_outermost_scope(debug_info, filename, 23)

    def test_in_function(self):
        debug_info, filename = self._get_debug_info()
        self.run_test_in_function(debug_info, filename, 19)

    def test_in_method(self):
        debug_info, filename = self._get_debug_info()
        self.run_test_in_method(debug_info, filename, 14)
