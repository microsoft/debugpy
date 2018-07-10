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


class ExceptionTests(LifecycleTestsBase):

    def run_test_not_breaking_into_handled_exceptions(self, debug_info):
        excbreakpoints = [{'filters': ['uncaught']}]
        options = {'debugOptions': ['RedirectOutput']}

        with self.start_debugging(debug_info) as dbg:
            (_, req_attach, _, _, _, _
             ) = lifecycle_handshake(dbg.session, debug_info.starttype,
                                     excbreakpoints=excbreakpoints,
                                     options=options)

        received = list(_strip_newline_output_events(dbg.session.received))
        self.assert_contains(received, [
            self.new_event('output', category='stdout', output='end'),
            self.new_event('exited', exitCode=0),
            self.new_event('terminated'),
        ])

    def run_test_breaking_into_handled_exceptions(self, debug_info):
        excbreakpoints = [{'filters': ['raised', 'uncaught']}]
        options = {'debugOptions': ['RedirectOutput']}

        with self.start_debugging(debug_info) as dbg:
            stopped = dbg.session.get_awaiter_for_event('stopped')
            (_, req_launch_attach, _, _, _, _
             ) = lifecycle_handshake(dbg.session, debug_info.starttype,
                                     excbreakpoints=excbreakpoints,
                                     options=options,
                                     threads=True)

            Awaitable.wait_all(req_launch_attach, stopped)
            self.assertEqual(stopped.event.body['text'], 'ArithmeticError')
            self.assertIn("ArithmeticError('Hello'",
                          stopped.event.body['description'])

            thread_id = stopped.event.body['threadId']
            req_exc_info = dbg.session.send_request(
                'exceptionInfo',
                threadId=thread_id,
            )
            req_exc_info.wait()
            exc_info = req_exc_info.resp.body

            self.assert_is_subset(exc_info, {
                'exceptionId': 'ArithmeticError',
                'breakMode': 'always',
                'details': {
                    'typeName': 'ArithmeticError',
                    # 'source': debug_info.filename
                }
            })

            continued = dbg.session.get_awaiter_for_event('continued')
            dbg.session.send_request(
                'continue',
                threadId=thread_id,
            ).wait()
            Awaitable.wait_all(continued)

        received = list(_strip_newline_output_events(dbg.session.received))
        self.assert_contains(received, [
            self.new_event('continued', threadId=thread_id),
            self.new_event('output', category='stdout', output='end'),
            self.new_event('exited', exitCode=0),
            self.new_event('terminated'),
        ])


class LaunchFileTests(ExceptionTests):

    def test_not_breaking_into_handled_exceptions(self):
        filename = TEST_FILES.resolve('handled_exceptions_launch.py')
        cwd = os.path.dirname(filename)
        self.run_test_not_breaking_into_handled_exceptions(
            DebugInfo(filename=filename, cwd=cwd))

    def test_breaking_into_handled_exceptions(self):
        filename = TEST_FILES.resolve('handled_exceptions_launch.py')
        cwd = os.path.dirname(filename)
        self.run_test_breaking_into_handled_exceptions(
            DebugInfo(filename=filename, cwd=cwd))


class LaunchModuleExceptionLifecycleTests(ExceptionTests):

    def test_breaking_into_handled_exceptions(self):
        module_name = 'mypkg_launch1'
        env = TEST_FILES.env_with_py_path()
        cwd = TEST_FILES.parent.root
        self.run_test_breaking_into_handled_exceptions(
            DebugInfo(modulename=module_name, env=env, cwd=cwd))

    def test_not_breaking_into_handled_exceptions(self):
        module_name = 'mypkg_launch1'
        env = TEST_FILES.env_with_py_path()
        cwd = TEST_FILES.parent.root
        self.run_test_not_breaking_into_handled_exceptions(
            DebugInfo(modulename=module_name, env=env, cwd=cwd))


class ServerAttachExceptionLifecycleTests(ExceptionTests):

    def test_breaking_into_handled_exceptions(self):
        filename = TEST_FILES.resolve('handled_exceptions_launch.py')
        cwd = os.path.dirname(filename)
        argv = ['localhost', str(PORT)]
        self.run_test_breaking_into_handled_exceptions(
            DebugInfo(
                filename=filename,
                cwd=cwd,
                starttype='attach',
                argv=argv,
            ))

    def test_not_breaking_into_handled_exceptions(self):
        filename = TEST_FILES.resolve('handled_exceptions_launch.py')
        cwd = os.path.dirname(filename)
        argv = ['localhost', str(PORT)]
        self.run_test_not_breaking_into_handled_exceptions(
            DebugInfo(
                filename=filename,
                cwd=cwd,
                starttype='attach',
                argv=argv,
            ))


class PTVSDAttachExceptionLifecycleTests(ExceptionTests):

    def test_breaking_into_handled_exceptions(self):
        filename = TEST_FILES.resolve('handled_exceptions_attach.py')
        cwd = os.path.dirname(filename)
        argv = ['localhost', str(PORT)]
        self.run_test_breaking_into_handled_exceptions(
            DebugInfo(
                filename=filename,
                attachtype='import',
                cwd=cwd,
                starttype='attach',
                argv=argv,
            ))

    @unittest.skip('Needs fixing in #609')
    def test_not_breaking_into_handled_exceptions(self):
        filename = TEST_FILES.resolve('handled_exceptions_attach.py')
        cwd = os.path.dirname(filename)
        argv = ['localhost', str(PORT)]
        self.run_test_not_breaking_into_handled_exceptions(
            DebugInfo(
                filename=filename,
                attachtype='import',
                cwd=cwd,
                starttype='attach',
                argv=argv,
            ))


class ServerAttachModuleExceptionLifecycleTests(ExceptionTests):

    def test_breaking_into_handled_exceptions(self):
        module_name = 'mypkg_launch1'
        env = TEST_FILES.env_with_py_path()
        cwd = TEST_FILES.root
        argv = ['localhost', str(PORT)]
        self.run_test_breaking_into_handled_exceptions(
            DebugInfo(
                modulename=module_name,
                env=env,
                cwd=cwd,
                argv=argv,
                starttype='attach',
            ))

    def test_not_breaking_into_handled_exceptions(self):
        module_name = 'mypkg_launch1'
        env = TEST_FILES.env_with_py_path()
        cwd = TEST_FILES.root
        argv = ['localhost', str(PORT)]
        self.run_test_not_breaking_into_handled_exceptions(
            DebugInfo(
                modulename=module_name,
                env=env,
                cwd=cwd,
                argv=argv,
                starttype='attach',
            ))


@unittest.skip('Needs fixing')
class PTVSDAttachModuleExceptionLifecycleTests(ExceptionTests):

    def test_breaking_into_handled_exceptions(self):
        module_name = 'mypkg_attach1'
        env = TEST_FILES.env_with_py_path()
        cwd = TEST_FILES.root
        argv = ['localhost', str(PORT)]
        self.run_test_breaking_into_handled_exceptions(
            DebugInfo(
                modulename=module_name,
                env=env,
                cwd=cwd,
                argv=argv,
                attachtype='import',
                starttype='attach',
            ))

    def test_not_breaking_into_handled_exceptions(self):
        module_name = 'mypkg_attach1'
        env = TEST_FILES.env_with_py_path()
        cwd = TEST_FILES.root
        argv = ['localhost', str(PORT)]
        self.run_test_not_breaking_into_handled_exceptions(
            DebugInfo(
                modulename=module_name,
                env=env,
                cwd=cwd,
                argv=argv,
                attachtype='import',
                starttype='attach',
            ))
