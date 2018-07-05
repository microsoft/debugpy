import os
import os.path
import unittest

from ptvsd.wrapper import INITIALIZE_RESPONSE  # noqa
from tests.helpers.debugsession import Awaitable

from . import (_strip_newline_output_events, lifecycle_handshake,
               LifecycleTestsBase, DebugInfo, ROOT, PORT)

TEST_FILES_DIR = os.path.join(ROOT, 'tests', 'resources', 'system_tests',
                              'test_basic')
TEST_TERMINATION_FILES_DIR = os.path.join(ROOT, 'tests', 'resources',
                                          'system_tests', 'test_terminate')


class LaunchLifecycleTests(LifecycleTestsBase):
    def run_test_output(self, debug_info):
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

    def test_with_output(self):
        filename = os.path.join(TEST_FILES_DIR, 'test_output', 'output.py')
        cwd = os.path.dirname(filename)
        self.run_test_output(DebugInfo(filename=filename, cwd=cwd))

    def run_test_arguments(self, debug_info, expected_args):
        options = {"debugOptions": ["RedirectOutput"]}

        with self.start_debugging(debug_info) as dbg:
            (_, _, _, _, _, _) = lifecycle_handshake(
                dbg.session, debug_info.starttype, options=options)

        received = list(_strip_newline_output_events(dbg.session.received))
        expected_output = "{}, {}".format(len(expected_args), expected_args)
        self.assert_contains(
            received,
            [
                self.new_event(
                    "output", category="stdout", output=expected_output)
            ],
        )

    def test_arguments(self):
        filename = os.path.join(TEST_FILES_DIR, 'test_args',
                                'launch_with_args.py')
        cwd = os.path.dirname(filename)
        argv = ['arg1', 'arg2']
        self.run_test_arguments(
            DebugInfo(filename=filename, cwd=cwd, argv=argv),
            [filename] + argv)

    def run_test_termination(self, debug_info):
        with self.start_debugging(debug_info) as dbg:
            session = dbg.session

            exited = session.get_awaiter_for_event('exited')
            terminated = session.get_awaiter_for_event('terminated')

            (_, req_launch, _, _, _, _) = lifecycle_handshake(
                dbg.session, debug_info.starttype, threads=True)

            Awaitable.wait_all(req_launch,
                               session.get_awaiter_for_event('thread'))  # noqa
            disconnect = session.send_request("disconnect")

            Awaitable.wait_all(exited, terminated, disconnect)

    @unittest.skip('Broken')
    def test_termination(self):
        filename = os.path.join(TEST_TERMINATION_FILES_DIR, 'simple.py')
        cwd = os.path.dirname(filename)
        self.run_test_termination(DebugInfo(filename=filename, cwd=cwd))

    def run_test_without_output(self, debug_info):
        options = {"debugOptions": ["RedirectOutput"]}

        with self.start_debugging(debug_info) as dbg:
            (_, _, _, _, _, _) = lifecycle_handshake(
                dbg.session,
                debug_info.starttype,
                options=options,
                threads=True)

        received = list(_strip_newline_output_events(dbg.session.received))

        out = self.find_events(received, 'output', {'category': 'stdout'})
        err = self.find_events(received, 'output', {'category': 'stderr'})
        self.assertEqual(len(out + err), 0)

    def test_without_output(self):
        filename = os.path.join(TEST_FILES_DIR, 'test_without_output',
                                'output.py')
        cwd = os.path.dirname(filename)
        self.run_test_without_output(DebugInfo(filename=filename, cwd=cwd))


class LaunchModuleLifecycleTests(LaunchLifecycleTests):
    def test_with_output(self):
        module_name = 'mymod_launch1'
        cwd = os.path.join(TEST_FILES_DIR, 'test_output')
        env = {"PYTHONPATH": cwd}
        self.run_test_output(
            DebugInfo(modulename=module_name, env=env, cwd=cwd))

    def test_without_output(self):
        module_name = 'mymod_launch1'
        cwd = os.path.join(TEST_FILES_DIR, 'test_without_output')
        env = {"PYTHONPATH": cwd}
        self.run_test_without_output(
            DebugInfo(modulename=module_name, env=env, cwd=cwd))

    @unittest.skip('Broken')
    def test_termination(self):
        module_name = 'mymod_launch1'
        cwd = TEST_TERMINATION_FILES_DIR
        env = {"PYTHONPATH": cwd}
        self.run_test_output(
            DebugInfo(modulename=module_name, env=env, cwd=cwd))
        self.run_test_termination(DebugInfo(modulename=module_name, cwd=cwd))

    @unittest.skip('Broken')
    def test_arguments(self):
        module_name = 'mymod_launch1'
        cwd = os.path.join(TEST_FILES_DIR, 'test_args')
        env = {"PYTHONPATH": cwd}
        argv = ['arg1', 'arg2']
        self.run_test_arguments(
            DebugInfo(modulename=module_name, env=env, cwd=cwd, argv=argv),
            ['-m'] + argv)


class ServerAttachLifecycleTests(LaunchLifecycleTests):
    def test_with_output(self):
        filename = os.path.join(TEST_FILES_DIR, 'test_output', 'output.py')
        cwd = os.path.dirname(filename)
        argv = ['localhost', str(PORT)]
        self.run_test_output(
            DebugInfo(
                filename=filename, cwd=cwd, starttype='attach', argv=argv))

    def test_without_output(self):
        filename = os.path.join(TEST_FILES_DIR, 'test_without_output',
                                'output.py')
        cwd = os.path.dirname(filename)
        argv = ['localhost', str(PORT)]
        self.run_test_without_output(
            DebugInfo(
                filename=filename, cwd=cwd, starttype='attach', argv=argv))

    @unittest.skip('Needs to be fixed')
    def test_not_breaking_into_handled_exceptions(self):
        pass

    @unittest.skip('No need to test')
    def test_termination(self):
        pass

    @unittest.skip('No need to test')
    def test_arguments(self):
        pass


class PTVSDAttachLifecycleTests(LaunchLifecycleTests):
    def test_with_output(self):
        filename = os.path.join(TEST_FILES_DIR, 'test_output',
                                'attach_output.py')
        cwd = os.path.dirname(filename)
        argv = ['localhost', str(PORT)]
        self.run_test_output(
            DebugInfo(
                filename=filename,
                attachtype='import',
                cwd=cwd,
                starttype='attach',
                argv=argv))

    def test_without_output(self):
        filename = os.path.join(TEST_FILES_DIR, 'test_without_output',
                                'attach_output.py')
        cwd = os.path.dirname(filename)
        argv = ['localhost', str(PORT)]
        self.run_test_without_output(
            DebugInfo(
                filename=filename,
                attachtype='import',
                cwd=cwd,
                starttype='attach',
                argv=argv))

    @unittest.skip('No need to test')
    def test_termination(self):
        pass

    @unittest.skip('No need to test')
    def test_arguments(self):
        pass


class ServerAttachModuleLifecycleTests(LaunchLifecycleTests):  # noqa
    def test_with_output(self):
        module_name = 'mymod_launch1'
        cwd = os.path.join(TEST_FILES_DIR, 'test_output')
        env = {"PYTHONPATH": cwd}
        argv = ['localhost', str(PORT)]
        self.run_test_output(
            DebugInfo(
                modulename=module_name,
                env=env,
                cwd=cwd,
                argv=argv,
                starttype='attach'))

    def test_without_output(self):
        module_name = 'mymod_launch1'
        cwd = os.path.join(TEST_FILES_DIR, 'test_without_output')
        env = {"PYTHONPATH": cwd}
        argv = ['localhost', str(PORT)]
        self.run_test_without_output(
            DebugInfo(
                modulename=module_name,
                env=env,
                cwd=cwd,
                argv=argv,
                starttype='attach'))

    @unittest.skip('No need to test')
    def test_termination(self):
        pass

    @unittest.skip('No need to test')
    def test_arguments(self):
        pass


@unittest.skip('Needs fixing')
class PTVSDAttachModuleLifecycleTests(LaunchLifecycleTests):  # noqa
    def test_with_output(self):
        module_name = 'mymod_attach1'
        cwd = os.path.join(TEST_FILES_DIR, 'test_output')
        env = {"PYTHONPATH": cwd}
        argv = ['localhost', str(PORT)]
        self.run_test_output(
            DebugInfo(
                modulename=module_name,
                env=env,
                cwd=cwd,
                argv=argv,
                attachtype='import',
                starttype='attach'))

    def test_without_output(self):
        module_name = 'mymod_attach1'
        cwd = os.path.join(TEST_FILES_DIR, 'test_without_output')
        env = {"PYTHONPATH": cwd}
        argv = ['localhost', str(PORT)]
        self.run_test_without_output(
            DebugInfo(
                modulename=module_name,
                env=env,
                cwd=cwd,
                argv=argv,
                attachtype='import',
                starttype='attach'))

    @unittest.skip('No need to test')
    def test_termination(self):
        pass

    @unittest.skip('No need to test')
    def test_arguments(self):
        pass
