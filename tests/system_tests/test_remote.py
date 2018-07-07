import os
import os.path
import socket

from . import (_strip_newline_output_events, lifecycle_handshake,
               LifecycleTestsBase, DebugInfo, ROOT, PORT)

TEST_FILES_DIR = os.path.join(ROOT, 'tests', 'resources', 'system_tests',
                              'test_basic')


class RemoteTests(LifecycleTestsBase):
    def run_test_attach(self, debug_info):
        options = {"debugOptions": ["RedirectOutput"]}

        with self.start_debugging(debug_info) as dbg:
            (_, _, _, _, _, _) = lifecycle_handshake(
                dbg.session, debug_info.starttype, options=options)

        received = list(_strip_newline_output_events(dbg.session.received))
        self.assert_contains(
            received,
            [
                self.new_event("output", category="stdout", output="yes"),
                self.new_event("output", category="stderr", output="no"),
            ],
        )


class AttachFileTests(RemoteTests):
    def test_attach_localhost(self):
        filename = os.path.join(TEST_FILES_DIR, 'test_output',
                                'attach_output.py')
        cwd = os.path.dirname(filename)
        argv = ['localhost', str(PORT)]
        self.run_test_attach(
            DebugInfo(
                filename=filename,
                attachtype='import',
                cwd=cwd,
                starttype='attach',
                argv=argv))

    def test_attach_127001(self):
        filename = os.path.join(TEST_FILES_DIR, 'test_output',
                                'attach_output.py')
        cwd = os.path.dirname(filename)
        argv = ['127.0.0.1', str(PORT)]
        self.run_test_attach(
            DebugInfo(
                filename=filename,
                attachtype='import',
                cwd=cwd,
                starttype='attach',
                argv=argv))

    def test_attach_0000(self):
        filename = os.path.join(TEST_FILES_DIR, 'test_output',
                                'attach_output.py')
        cwd = os.path.dirname(filename)
        argv = ['0.0.0.0', str(PORT)]
        self.run_test_attach(
            DebugInfo(
                filename=filename,
                attachtype='import',
                cwd=cwd,
                starttype='attach',
                argv=argv))

    def test_attach_byip(self):
        filename = os.path.join(TEST_FILES_DIR, 'test_output',
                                'attach_output.py')
        cwd = os.path.dirname(filename)
        argv = ['0.0.0.0', str(PORT)]
        ip = socket.gethostbyname(socket.gethostname())
        self.run_test_attach(
            DebugInfo(
                filename=filename,
                attachtype='import',
                host=ip,
                cwd=cwd,
                starttype='attach',
                argv=argv))
