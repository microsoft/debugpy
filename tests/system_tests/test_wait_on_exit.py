import os
import os.path
import time

from tests.helpers.resource import TestResources
from . import (
    lifecycle_handshake, LifecycleTestsBase, DebugInfo,
)

TEST_FILES = TestResources.from_module(__name__)


class WaitOnExitTests(LifecycleTestsBase):
    def _wait_for_output(self, session):
        for _ in range(50):
            time.sleep(0.1)
            out = '\t'.join(e.body['output'] for e in
                            self.find_events(session.received, 'output')
                            if e.body['category'] == 'stdout')
            if not out.find('Ready') == -1:
                return True
        return False

    def run_test_wait_on_exit(self, debug_info, dbg_options, expect_timeout):
        options = {'debugOptions': ['RedirectOutput'] + dbg_options}
        launched = False
        exception_occurred = False
        try:
            with self.start_debugging(debug_info) as dbg:
                session = dbg.session
                (_, req_launch_attach, _, _, _, _
                 ) = lifecycle_handshake(session, debug_info.starttype,
                                         options=options)
                req_launch_attach.wait(timeout=2.0)

                # wait for the test program initiate exit
                self.assertTrue(self._wait_for_output(session))
                launched = True
        except Exception as ex:
            dbg.adapter._proc.terminate()
            if not launched:
                raise
            if not expect_timeout:
                raise
            exception_occurred = True
            text = 'Timeout waiting for process to die'
            self.assertTrue(ex.args[0].find(text) > -1)
        self.assertEqual(expect_timeout, exception_occurred)


class LaunchFileWaitOnExitTests(WaitOnExitTests):
    def test_wait_on_normal_exit_enabled(self):
        filename = TEST_FILES.resolve('waitonexit.py')
        cwd = os.path.dirname(filename)
        env = {'PTVSD_NORMAL_EXIT': 'True'}
        debug_info = DebugInfo(filename=filename, cwd=cwd, env=env)
        self.run_test_wait_on_exit(debug_info,
                                   dbg_options=['WaitOnNormalExit'],
                                   expect_timeout=True)

    def test_wait_on_normal_exit_disabled(self):
        filename = TEST_FILES.resolve('waitonexit.py')
        cwd = os.path.dirname(filename)
        env = {'PTVSD_NORMAL_EXIT': 'True'}
        debug_info = DebugInfo(filename=filename, cwd=cwd, env=env)
        self.run_test_wait_on_exit(debug_info,
                                   dbg_options=[],
                                   expect_timeout=False)

    def test_wait_on_abnormal_exit_enabled(self):
        filename = TEST_FILES.resolve('waitonexit.py')
        cwd = os.path.dirname(filename)
        debug_info = DebugInfo(filename=filename, cwd=cwd)
        self.run_test_wait_on_exit(debug_info,
                                   dbg_options=['WaitOnAbnormalExit'],
                                   expect_timeout=True)

    def test_wait_on_abnormal_exit_disabled(self):
        filename = TEST_FILES.resolve('waitonexit.py')
        cwd = os.path.dirname(filename)
        debug_info = DebugInfo(filename=filename, cwd=cwd)
        self.run_test_wait_on_exit(debug_info,
                                   dbg_options=['WaitOnNormalExit'],
                                   expect_timeout=False)


class LaunchModuleWaitOnExitTests(WaitOnExitTests):
    def test_wait_on_normal_exit_enabled(self):
        module_name = 'waitonexit'
        cwd = TEST_FILES.parent.root
        env = TEST_FILES.env_with_py_path()
        env['PTVSD_NORMAL_EXIT'] = 'True'
        debug_info = DebugInfo(modulename=module_name, env=env, cwd=cwd)
        self.run_test_wait_on_exit(debug_info,
                                   dbg_options=['WaitOnNormalExit'],
                                   expect_timeout=True)

    def test_wait_on_normal_exit_disabled(self):
        module_name = 'waitonexit'
        cwd = TEST_FILES.parent.root
        env = TEST_FILES.env_with_py_path()
        env['PTVSD_NORMAL_EXIT'] = 'True'
        debug_info = DebugInfo(modulename=module_name, env=env, cwd=cwd)
        self.run_test_wait_on_exit(debug_info,
                                   dbg_options=[],
                                   expect_timeout=False)

    def test_wait_on_abnormal_exit_enabled(self):
        module_name = 'waitonexit'
        cwd = TEST_FILES.parent.root
        env = TEST_FILES.env_with_py_path()
        debug_info = DebugInfo(modulename=module_name, env=env, cwd=cwd)
        self.run_test_wait_on_exit(debug_info,
                                   dbg_options=['WaitOnAbnormalExit'],
                                   expect_timeout=True)

    def test_wait_on_abnormal_exit_disabled(self):
        module_name = 'waitonexit'
        cwd = TEST_FILES.parent.root
        env = TEST_FILES.env_with_py_path()
        debug_info = DebugInfo(modulename=module_name, env=env, cwd=cwd)
        self.run_test_wait_on_exit(debug_info,
                                   dbg_options=['WaitOnNormalExit'],
                                   expect_timeout=False)
