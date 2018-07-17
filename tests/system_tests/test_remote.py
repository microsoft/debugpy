import os
import os.path
import signal
import sys

from tests.helpers.resource import TestResources
from tests.helpers.script import find_line
from tests.helpers.socket import resolve_hostname
from . import (
    _strip_newline_output_events, lifecycle_handshake,
    LifecycleTestsBase, DebugInfo, PORT,
)


TEST_FILES = TestResources.from_module('tests.system_tests.test_basic')
WITH_OUTPUT = TEST_FILES.sub('test_output')
SYSTEM_TEST_FILES = TestResources.from_module('tests.system_tests')
WITH_TEST_FORVER = SYSTEM_TEST_FILES.sub('test_forever')


class RemoteTests(LifecycleTestsBase):
    def _assert_stacktrace_is_subset(self, stacktrace, expected_stacktrace):
        # Ignore path case on Windows.
        if sys.platform == 'win32':
            for frame in stacktrace.get('stackFrames'):
                frame['source']['path'] = frame['source'].get('path', '').upper() # noqa
            for frame in expected_stacktrace.get('stackFrames'):
                frame['source']['path'] = frame['source'].get('path', '').upper() # noqa

        self.assert_is_subset(stacktrace, expected_stacktrace)

    def run_test_attach(self, debug_info):
        options = {'debugOptions': ['RedirectOutput']}

        with self.start_debugging(debug_info) as dbg:
            lifecycle_handshake(dbg.session, debug_info.starttype,
                                options=options)

        received = list(_strip_newline_output_events(dbg.session.received))
        self.assert_contains(received, [
            self.new_event('output', category='stdout', output='yes'),
            self.new_event('output', category='stderr', output='no'),
        ])

    def run_test_source_references(self,
                                   debug_info,
                                   expected_stacktrace,
                                   path_mappings=[],
                                   debug_options=[]):
        options = {
            'debugOptions': debug_options,
            'pathMappings': path_mappings
        }

        with open(debug_info.filename) as scriptfile:
            script = scriptfile.read()
        bp = find_line(script, 'bp')

        with self.start_debugging(debug_info) as dbg:
            lifecycle_handshake(dbg.session, debug_info.starttype,
                                options=options,
                                threads=True)

            # wait till we enter the for loop.
            with dbg.session.wait_for_event('stopped') as result:
                arguments = {
                    'source': {
                        'name': os.path.basename(debug_info.filename),
                        'path': debug_info.filename
                    },
                    'lines': [bp],
                    'breakpoints': [{'line': bp}]
                }
                dbg.session.send_request('setBreakpoints', **arguments)
            event = result['msg']
            tid = event.body['threadId']
            req_stacktrace = dbg.session.send_request(
                'stackTrace',
                threadId=tid,
            )
            req_stacktrace.wait()
            stacktrace = req_stacktrace.resp.body
            req_continue = dbg.session.send_request('continue', threadId=tid)
            req_continue.wait()

            # Kill remove program.
            os.kill(dbg.adapter.pid, signal.SIGTERM)

        self._assert_stacktrace_is_subset(stacktrace, expected_stacktrace)


class AttachFileTests(RemoteTests):

    def test_attach_localhost(self):
        filename = WITH_OUTPUT.resolve('attach_output.py')
        cwd = os.path.dirname(filename)
        argv = ['localhost', str(PORT)]
        self.run_test_attach(
            DebugInfo(
                filename=filename,
                attachtype='import',
                cwd=cwd,
                starttype='attach',
                argv=argv,
            ),
        )

    def test_attach_127001(self):
        filename = WITH_OUTPUT.resolve('attach_output.py')
        cwd = os.path.dirname(filename)
        argv = ['127.0.0.1', str(PORT)]
        self.run_test_attach(
            DebugInfo(
                filename=filename,
                attachtype='import',
                cwd=cwd,
                starttype='attach',
                argv=argv,
            ),
        )

    def test_attach_0000(self):
        filename = WITH_OUTPUT.resolve('attach_output.py')
        cwd = os.path.dirname(filename)
        argv = ['0.0.0.0', str(PORT)]
        self.run_test_attach(
            DebugInfo(
                filename=filename,
                attachtype='import',
                cwd=cwd,
                starttype='attach',
                argv=argv,
            ),
        )

    def test_attach_byip(self):
        filename = WITH_OUTPUT.resolve('attach_output.py')
        cwd = os.path.dirname(filename)
        argv = ['0.0.0.0', str(PORT)]
        ip = resolve_hostname()

        self.run_test_attach(
            DebugInfo(
                filename=filename,
                attachtype='import',
                host=ip,
                cwd=cwd,
                starttype='attach',
                argv=argv,
            ),
        )

    def test_source_references_should_be_returned_without_path_mappings(self):
        filename = WITH_TEST_FORVER.resolve('attach_forever.py')
        cwd = os.path.dirname(filename)
        argv = ['localhost', str(PORT)]
        expected_stacktrace = {
            'stackFrames': [{
                'source': {
                    'path': filename,
                    'sourceReference': 1,
                }
            }],
        }
        self.run_test_source_references(
            DebugInfo(
                filename=filename,
                attachtype='import',
                cwd=cwd,
                starttype='attach',
                argv=argv,
            ),
            expected_stacktrace,
        )

    def test_source_references_should_not_be_returned_with_path_mappings(self):
        filename = WITH_TEST_FORVER.resolve('attach_forever.py')
        cwd = os.path.dirname(filename)
        argv = ['localhost', str(PORT)]
        path_mappings = [{
            'localRoot': os.path.dirname(filename),
            'remoteRoot': os.path.dirname(filename)
        }]
        expected_stacktrace = {
            'stackFrames': [{
                'source': {
                    'path': filename,
                    'sourceReference': 0,
                }
            }],
        }
        self.run_test_source_references(
            DebugInfo(
                filename=filename,
                attachtype='import',
                cwd=cwd,
                starttype='attach',
                argv=argv,
                #verbose=True,
            ),
            expected_stacktrace,
            path_mappings,
        )

    def test_source_references_should_be_returned_with_invalid_path_mappings(
            self):
        filename = WITH_TEST_FORVER.resolve('attach_forever.py')
        cwd = os.path.dirname(filename)
        argv = ['localhost', str(PORT)]
        path_mappings = [{
            'localRoot': os.path.dirname(__file__),
            'remoteRoot': os.path.dirname(__file__)
        }]
        expected_stacktrace = {
            'stackFrames': [{
                'source': {
                    'path': filename,
                    'sourceReference': 1,
                }
            }],
        }
        self.run_test_source_references(
            DebugInfo(
                filename=filename,
                attachtype='import',
                cwd=cwd,
                starttype='attach',
                argv=argv,
            ),
            expected_stacktrace,
            path_mappings,
        )

    def test_source_references_should_be_returned_with_win_client(self):
        filename = WITH_TEST_FORVER.resolve('attach_forever.py')
        cwd = os.path.dirname(filename)
        argv = ['localhost', str(PORT)]
        client_dir = 'C:\\Development\\Projects\\src\\sub dir'
        path_mappings = [{
            'localRoot': client_dir,
            'remoteRoot': os.path.dirname(filename)
        }]
        expected_stacktrace = {
            'stackFrames': [{
                'source': {
                    'path': client_dir + '\\' + os.path.basename(filename),
                    'sourceReference': 0,
                }
            }],
        }
        self.run_test_source_references(
            DebugInfo(
                filename=filename,
                attachtype='import',
                cwd=cwd,
                starttype='attach',
                argv=argv,
            ),
            expected_stacktrace,
            path_mappings=path_mappings,
            debug_options=['WindowsClient'],
        )

    def test_source_references_should_be_returned_with_unix_client(self):
        filename = WITH_TEST_FORVER.resolve('attach_forever.py')
        cwd = os.path.dirname(filename)
        argv = ['localhost', str(PORT)]
        client_dir = '/Users/PeterSmith/projects/src/sub dir'
        path_mappings = [{
            'localRoot': client_dir,
            'remoteRoot': os.path.dirname(filename)
        }]
        expected_stacktrace = {
            'stackFrames': [{
                'source': {
                    'path': client_dir + '/' + os.path.basename(filename),
                    'sourceReference': 0,
                }
            }],
        }
        self.run_test_source_references(
            DebugInfo(
                filename=filename,
                attachtype='import',
                cwd=cwd,
                starttype='attach',
                argv=argv,
            ),
            expected_stacktrace,
            path_mappings=path_mappings,
            debug_options=['UnixClient'],
        )
