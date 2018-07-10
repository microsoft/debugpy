import os
import os.path
import unittest

from tests.helpers.debugsession import Awaitable
from tests.helpers.resource import TestResources
from . import (
    _strip_newline_output_events, lifecycle_handshake,
    LifecycleTestsBase, DebugInfo, PORT,
)


TEST_FILES = TestResources.from_module(__name__)
WITH_OUTPUT = TEST_FILES.sub('test_output')
WITHOUT_OUTPUT = TEST_FILES.sub('test_without_output')
WITH_ARGS = TEST_FILES.sub('test_args')
TEST_TERMINATION_FILES = TestResources.from_module(
    'tests.system_tests.test_terminate')


class BasicTests(LifecycleTestsBase):

    def run_test_output(self, debug_info):
        options = {'debugOptions': ['RedirectOutput']}

        with self.start_debugging(debug_info) as dbg:
            lifecycle_handshake(dbg.session, debug_info.starttype,
                                options=options)

        received = list(_strip_newline_output_events(dbg.session.received))
        self.assert_contains(received, [
            self.new_event('output', category='stdout', output='yes'),
            self.new_event('output', category='stderr', output='no'),
        ])

    def run_test_arguments(self, debug_info, expected_args):
        options = {'debugOptions': ['RedirectOutput']}

        with self.start_debugging(debug_info) as dbg:
            lifecycle_handshake(dbg.session, debug_info.starttype,
                                options=options)

        received = list(_strip_newline_output_events(dbg.session.received))
        expected_output = '{}, {}'.format(len(expected_args), expected_args)
        self.assert_contains(received, [
            self.new_event(
                'output', category='stdout', output=expected_output),
        ])

    def run_test_termination(self, debug_info):
        with self.start_debugging(debug_info) as dbg:
            session = dbg.session

            exited = session.get_awaiter_for_event('exited')
            terminated = session.get_awaiter_for_event('terminated')

            (_, req_launch, _, _, _, _
             ) = lifecycle_handshake(dbg.session, debug_info.starttype,
                                     threads=True)

            Awaitable.wait_all(req_launch,
                               session.get_awaiter_for_event('thread'))
            disconnect = session.send_request('disconnect')

            Awaitable.wait_all(exited, terminated, disconnect)

    def run_test_without_output(self, debug_info):
        options = {'debugOptions': ['RedirectOutput']}

        with self.start_debugging(debug_info) as dbg:
            lifecycle_handshake(dbg.session, debug_info.starttype,
                                options=options,
                                threads=True)

        received = list(_strip_newline_output_events(dbg.session.received))

        out = self.find_events(received, 'output', {'category': 'stdout'})
        err = self.find_events(received, 'output', {'category': 'stderr'})
        self.assertEqual(len(out + err), 0)


class LaunchFileTests(BasicTests):

    def test_with_output(self):
        filename = WITH_OUTPUT.resolve('output.py')
        cwd = os.path.dirname(filename)
        self.run_test_output(DebugInfo(filename=filename, cwd=cwd))

    def test_arguments(self):
        filename = WITH_ARGS.resolve('launch_with_args.py')
        cwd = os.path.dirname(filename)
        argv = ['arg1', 'arg2']
        self.run_test_arguments(
            DebugInfo(filename=filename, cwd=cwd, argv=argv),
            [filename] + argv,
        )

    @unittest.skip('Broken')
    def test_termination(self):
        filename = TEST_TERMINATION_FILES.resolve('simple.py')
        cwd = os.path.dirname(filename)
        self.run_test_termination(
            DebugInfo(filename=filename, cwd=cwd),
        )

    def test_without_output(self):
        filename = WITHOUT_OUTPUT.resolve('output.py')
        cwd = os.path.dirname(filename)
        self.run_test_without_output(
            DebugInfo(filename=filename, cwd=cwd),
        )


class LaunchPackageTests(BasicTests):

    def test_with_output(self):
        module_name = 'mypkg_launch1'
        cwd = WITH_OUTPUT.root
        env = WITH_OUTPUT.env_with_py_path()
        self.run_test_output(
            DebugInfo(modulename=module_name, env=env, cwd=cwd),
        )

    def test_without_output(self):
        module_name = 'mypkg_launch1'
        cwd = WITHOUT_OUTPUT.root
        env = WITHOUT_OUTPUT.env_with_py_path()
        self.run_test_without_output(
            DebugInfo(modulename=module_name, env=env, cwd=cwd),
        )

    @unittest.skip('Broken')
    def test_termination(self):
        module_name = 'mypkg_launch1'
        cwd = TEST_TERMINATION_FILES.root
        env = TEST_TERMINATION_FILES.env_with_py_path()
        self.run_test_output(
            DebugInfo(modulename=module_name, env=env, cwd=cwd),
        )
        self.run_test_termination(
            DebugInfo(modulename=module_name, cwd=cwd),
        )

    @unittest.skip('Broken')
    def test_arguments(self):
        module_name = 'mypkg_launch1'
        cwd = WITH_ARGS.root
        env = WITH_ARGS.env_with_py_path()
        argv = ['arg1', 'arg2']
        self.run_test_arguments(
            DebugInfo(modulename=module_name, env=env, cwd=cwd, argv=argv),
            ['-m'] + argv,
        )


class ServerAttachTests(BasicTests):

    def test_with_output(self):
        filename = WITH_OUTPUT.resolve('output.py')
        cwd = os.path.dirname(filename)
        argv = ['localhost', str(PORT)]
        self.run_test_output(
            DebugInfo(
                filename=filename,
                cwd=cwd,
                starttype='attach',
                argv=argv,
            ),
        )

    def test_without_output(self):
        filename = WITHOUT_OUTPUT.resolve('output.py')
        cwd = os.path.dirname(filename)
        argv = ['localhost', str(PORT)]
        self.run_test_without_output(
            DebugInfo(
                filename=filename,
                cwd=cwd,
                starttype='attach',
                argv=argv,
            ),
        )


class PTVSDAttachTests(BasicTests):

    def test_with_output(self):
        filename = WITH_OUTPUT.resolve('attach_output.py')
        cwd = os.path.dirname(filename)
        argv = ['localhost', str(PORT)]
        self.run_test_output(
            DebugInfo(
                filename=filename,
                attachtype='import',
                cwd=cwd,
                starttype='attach',
                argv=argv,
            ),
        )

    def test_without_output(self):
        filename = WITHOUT_OUTPUT.resolve('attach_output.py')
        cwd = os.path.dirname(filename)
        argv = ['localhost', str(PORT)]
        self.run_test_without_output(
            DebugInfo(
                filename=filename,
                attachtype='import',
                cwd=cwd,
                starttype='attach',
                argv=argv,
            ),
        )


class ServerAttachPackageTests(BasicTests):

    def test_with_output(self):
        module_name = 'mypkg_launch1'
        cwd = WITH_OUTPUT.root
        env = WITH_OUTPUT.env_with_py_path()
        argv = ['localhost', str(PORT)]
        self.run_test_output(
            DebugInfo(
                modulename=module_name,
                env=env,
                cwd=cwd,
                argv=argv,
                starttype='attach',
            ),
        )

    def test_without_output(self):
        module_name = 'mypkg_launch1'
        cwd = WITHOUT_OUTPUT.root
        env = WITHOUT_OUTPUT.env_with_py_path()
        argv = ['localhost', str(PORT)]
        self.run_test_without_output(
            DebugInfo(
                modulename=module_name,
                env=env,
                cwd=cwd,
                argv=argv,
                starttype='attach',
            ),
        )


class PTVSDAttachPackageTests(BasicTests):

    def test_with_output(self):
        #self.enable_verbose()
        module_name = 'mypkg_attach1'
        cwd = WITH_OUTPUT.root
        env = WITH_OUTPUT.env_with_py_path()
        argv = ['localhost', str(PORT)]
        self.run_test_output(
            DebugInfo(
                modulename=module_name,
                env=env,
                cwd=cwd,
                argv=argv,
                attachtype='import',
                starttype='attach',
            ),
        )

    def test_without_output(self):
        module_name = 'mypkg_attach1'
        cwd = WITHOUT_OUTPUT.root
        env = WITHOUT_OUTPUT.env_with_py_path()
        argv = ['localhost', str(PORT)]
        self.run_test_without_output(
            DebugInfo(
                modulename=module_name,
                env=env,
                cwd=cwd,
                argv=argv,
                attachtype='import',
                starttype='attach',
            ),
        )
