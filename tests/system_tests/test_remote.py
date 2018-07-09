import os
import os.path

from tests.helpers.resource import TestResources
from tests.helpers.socket import resolve_hostname
from . import (
    _strip_newline_output_events, lifecycle_handshake,
    LifecycleTestsBase, DebugInfo, PORT,
)


TEST_FILES = TestResources.from_module('tests.system_tests.test_basic')
WITH_OUTPUT = TEST_FILES.sub('test_output')


class RemoteTests(LifecycleTestsBase):

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
