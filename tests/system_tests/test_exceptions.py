import os
import os.path
import unittest

from tests.helpers.debugsession import Awaitable
from tests.helpers.resource import TestResources
from . import (
    _strip_newline_output_events,
    lifecycle_handshake,
    LifecycleTestsBase,
    DebugInfo,
    PORT,
)

TEST_FILES = TestResources.from_module(__name__)


class ExceptionTests(LifecycleTestsBase):
    def run_test_not_breaking_into_handled_exceptions(self, debug_info):
        excbreakpoints = [{'filters': ['uncaught']}]
        options = {'debugOptions': ['RedirectOutput']}

        with self.start_debugging(debug_info) as dbg:
            lifecycle_handshake(
                dbg.session,
                debug_info.starttype,
                excbreakpoints=excbreakpoints,
                options=options)

        received = list(_strip_newline_output_events(dbg.session.received))
        self.assert_contains(received, [
            self.new_event('output', category='stdout', output='end'),
            self.new_event('exited', exitCode=0),
            self.new_event('terminated'),
        ])

    def run_test_not_breaking_into_unhandled_exceptions(self, debug_info):
        excbreakpoints = [{'filters': []}]
        options = {'debugOptions': ['RedirectOutput']}

        with self.start_debugging(debug_info) as dbg:
            lifecycle_handshake(
                dbg.session,
                debug_info.starttype,
                excbreakpoints=excbreakpoints,
                options=options)

        received = list(_strip_newline_output_events(dbg.session.received))
        # TODO: Re-enable after fixing #685
        #self.assertEqual(
        #    len(self.find_events(received, 'output', {'category': 'stdout'})),
        #    1)
        std_errs = self.find_events(received, 'output', {'category': 'stderr'})
        self.assertGreaterEqual(len(std_errs), 1)
        std_err_msg = ''.join([msg.body['output'] for msg in std_errs])
        self.assertIn('ArithmeticError: Hello', std_err_msg)
        self.assert_contains(received, [
            # TODO: Re-enable after fixing #685
            # self.new_event('output', category='stdout', output='one'),
            self.new_event('exited', exitCode=0),
            self.new_event('terminated'),
        ])

    def run_test_breaking_into_handled_exceptions(self, debug_info,
                                                  expected_source_name):
        excbreakpoints = [{'filters': ['raised']}]
        options = {'debugOptions': ['RedirectOutput']}

        with self.start_debugging(debug_info) as dbg:
            stopped = dbg.session.get_awaiter_for_event('stopped')
            (_, req_launch_attach, _, _, _, _) = lifecycle_handshake(
                dbg.session,
                debug_info.starttype,
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

            self.assert_is_subset(
                exc_info, {
                    'exceptionId': 'ArithmeticError',
                    'breakMode': 'always',
                    'details': {
                        'typeName': 'ArithmeticError',
                        'source': expected_source_name
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

    def run_test_breaking_into_unhandled_exceptions(self, debug_info,
                                                    expected_source_name):
        excbreakpoints = [{'filters': ['uncaught']}]
        options = {'debugOptions': ['RedirectOutput']}

        with self.start_debugging(debug_info) as dbg:
            stopped = dbg.session.get_awaiter_for_event('stopped')
            (_, req_launch_attach, _, _, _, _) = lifecycle_handshake(
                dbg.session,
                debug_info.starttype,
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

            self.assert_is_subset(
                exc_info, {
                    'exceptionId': 'ArithmeticError',
                    'breakMode': 'unhandled',
                    'details': {
                        'typeName': 'ArithmeticError',
                        'source': expected_source_name
                    }
                })

            continued = dbg.session.get_awaiter_for_event('continued')
            dbg.session.send_request(
                'continue',
                threadId=thread_id,
            ).wait()
            Awaitable.wait_all(continued)

        received = list(_strip_newline_output_events(dbg.session.received))
        # TODO: Re-enable after fixing #685
        #self.assertEqual(
        #    len(self.find_events(received, 'output', {'category': 'stdout'})),
        #    1)
        std_errs = self.find_events(received, 'output', {'category': 'stderr'})
        self.assertGreaterEqual(len(std_errs), 1)
        std_err_msg = ''.join([msg.body['output'] for msg in std_errs])
        self.assertIn('ArithmeticError: Hello', std_err_msg)
        self.assert_contains(received, [
            self.new_event('continued', threadId=thread_id),
            # TODO: Re-enable after fixing #685
            # self.new_event('output', category='stdout', output='one'),
            self.new_event('exited', exitCode=0),
            self.new_event('terminated'),
        ])

    def run_test_breaking_into_raised_exceptions_only(self, debug_info,
                                                      expected_source_name):
        # NOTE: for this case we will be using a unhandled exception. The
        # behavior expected here is that it breaks once when the exception
        # was raised but not during postmortem
        excbreakpoints = [{'filters': ['raised']}]
        options = {'debugOptions': ['RedirectOutput']}

        with self.start_debugging(debug_info) as dbg:
            stopped = dbg.session.get_awaiter_for_event('stopped')
            (_, req_launch_attach, _, _, _, _
             ) = lifecycle_handshake(dbg.session, debug_info.starttype,
                                     excbreakpoints=excbreakpoints,
                                     options=options)

            Awaitable.wait_all(req_launch_attach, stopped)
            self.assertEqual(stopped.event.body['text'], 'ArithmeticError')
            self.assertIn("ArithmeticError('Hello'",
                          stopped.event.body['description'])

            thread_id = stopped.event.body['threadId']
            req_exc_info = dbg.session.send_request(
                'exceptionInfo',
                threadId=thread_id)
            req_exc_info.wait()
            exc_info = req_exc_info.resp.body

            self.assert_is_subset(exc_info, {
                'exceptionId': 'ArithmeticError',
                'breakMode': 'always',
                'details': {
                    'typeName': 'ArithmeticError',
                    'source': expected_source_name
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
            self.new_event('exited', exitCode=0),
            self.new_event('terminated'),
        ])

    def run_test_breaking_into_raised_and_unhandled_exceptions(
        self, debug_info, expected_source_name):
        excbreakpoints = [{'filters': ['raised', 'uncaught']}]
        options = {'debugOptions': ['RedirectOutput']}

        expected = {
            'exceptionId': 'ArithmeticError',
            'breakMode': 'always',
            'details': {
                'typeName': 'ArithmeticError',
                'source': expected_source_name
            }
        }

        with self.start_debugging(debug_info) as dbg:
            stopped = dbg.session.get_awaiter_for_event('stopped')
            (_, req_launch_attach, _, _, _, _
             ) = lifecycle_handshake(dbg.session, debug_info.starttype,
                                     excbreakpoints=excbreakpoints,
                                     options=options)

            Awaitable.wait_all(req_launch_attach, stopped)
            self.assertEqual(stopped.event.body['text'], 'ArithmeticError')
            self.assertIn("ArithmeticError('Hello'",
                          stopped.event.body['description'])

            thread_id = stopped.event.body['threadId']
            req_exc_info = dbg.session.send_request(
                'exceptionInfo',
                threadId=thread_id)
            req_exc_info.wait()
            self.assert_is_subset(req_exc_info.resp.body, expected)

            stopped2 = dbg.session.get_awaiter_for_event('stopped')
            continued = dbg.session.get_awaiter_for_event('continued')
            dbg.session.send_request(
                'continue',
                threadId=thread_id,
            ).wait()
            Awaitable.wait_all(stopped2, continued)

            # Second hit on uncaught exception
            self.assertEqual(stopped2.event.body['text'], 'ArithmeticError')
            self.assertIn("ArithmeticError('Hello'",
                          stopped2.event.body['description'])
            req_exc_info2 = dbg.session.send_request(
                'exceptionInfo',
                threadId=thread_id,
            )
            req_exc_info2.wait()
            self.assert_is_subset(req_exc_info2.resp.body, expected)

            continued2 = dbg.session.get_awaiter_for_event('continued')
            dbg.session.send_request(
                'continue',
                threadId=thread_id,
            ).wait()
            Awaitable.wait_all(continued2)

        received = list(_strip_newline_output_events(dbg.session.received))
        self.assert_contains(received, [
            self.new_event('continued', threadId=thread_id),
            self.new_event('continued', threadId=thread_id),  # expect 2 events
            self.new_event('exited', exitCode=0),
            self.new_event('terminated'),
        ])


class LaunchFileTests(ExceptionTests):
    def test_not_breaking_into_handled_exceptions(self):
        filename = TEST_FILES.resolve('handled_exceptions_launch.py')
        cwd = os.path.dirname(filename)
        self.run_test_not_breaking_into_handled_exceptions(
            DebugInfo(filename=filename, cwd=cwd))

    def test_not_breaking_into_unhandled_exceptions(self):
        filename = TEST_FILES.resolve('unhandled_exceptions_launch.py')
        cwd = os.path.dirname(filename)
        self.run_test_not_breaking_into_unhandled_exceptions(
            DebugInfo(filename=filename, cwd=cwd))

    def test_breaking_into_handled_exceptions(self):
        filename = TEST_FILES.resolve('handled_exceptions_launch.py')
        cwd = os.path.dirname(filename)
        self.run_test_breaking_into_handled_exceptions(
            DebugInfo(filename=filename, cwd=cwd), filename)

    def test_breaking_into_unhandled_exceptions(self):
        filename = TEST_FILES.resolve('unhandled_exceptions_launch.py')
        cwd = os.path.dirname(filename)
        self.run_test_breaking_into_unhandled_exceptions(
            DebugInfo(filename=filename, cwd=cwd), filename)

    def test_breaking_into_raised_exceptions_only(self):
        filename = TEST_FILES.resolve('unhandled_exceptions_launch.py')
        cwd = os.path.dirname(filename)
        self.run_test_breaking_into_raised_exceptions_only(
            DebugInfo(filename=filename, cwd=cwd), filename)

    def test_breaking_into_raised_and_unhandled_exceptions(self):
        filename = TEST_FILES.resolve('unhandled_exceptions_launch.py')
        cwd = os.path.dirname(filename)
        self.run_test_breaking_into_raised_and_unhandled_exceptions(
            DebugInfo(filename=filename, cwd=cwd), filename)


class LaunchModuleExceptionLifecycleTests(ExceptionTests):
    def test_not_breaking_into_handled_exceptions(self):
        module_name = 'mypkg_launch1'
        env = TEST_FILES.env_with_py_path()
        cwd = TEST_FILES.parent.root
        self.run_test_not_breaking_into_handled_exceptions(
            DebugInfo(modulename=module_name, env=env, cwd=cwd))

    def test_not_breaking_into_unhandled_exceptions(self):
        module_name = 'mypkg_launch_unhandled'
        env = TEST_FILES.env_with_py_path()
        cwd = TEST_FILES.parent.root
        self.run_test_not_breaking_into_unhandled_exceptions(
            DebugInfo(modulename=module_name, env=env, cwd=cwd))

    def test_breaking_into_handled_exceptions(self):
        module_name = 'mypkg_launch1'
        env = TEST_FILES.env_with_py_path()
        cwd = TEST_FILES.parent.root
        self.run_test_breaking_into_handled_exceptions(
            DebugInfo(modulename=module_name, env=env, cwd=cwd),
            os.path.join(TEST_FILES.root, module_name, '__init__.py'))

    def test_breaking_into_unhandled_exceptions(self):
        module_name = 'mypkg_launch_unhandled'
        env = TEST_FILES.env_with_py_path()
        cwd = TEST_FILES.parent.root
        self.run_test_breaking_into_unhandled_exceptions(
            DebugInfo(modulename=module_name, env=env, cwd=cwd),
            os.path.join(TEST_FILES.root, module_name, '__main__.py'))

    def test_breaking_into_raised_exceptions_only(self):
        module_name = 'mypkg_launch_unhandled'
        env = TEST_FILES.env_with_py_path()
        cwd = TEST_FILES.parent.root
        self.run_test_breaking_into_raised_exceptions_only(
            DebugInfo(modulename=module_name, env=env, cwd=cwd),
            os.path.join(TEST_FILES.root, module_name, '__main__.py'))

    def test_breaking_into_raised_and_unhandled_exceptions(self):
        module_name = 'mypkg_launch_unhandled'
        env = TEST_FILES.env_with_py_path()
        cwd = TEST_FILES.parent.root
        self.run_test_breaking_into_raised_and_unhandled_exceptions(
            DebugInfo(modulename=module_name, env=env, cwd=cwd),
            os.path.join(TEST_FILES.root, module_name, '__main__.py'))


class ServerAttachExceptionLifecycleTests(ExceptionTests):
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

    def test_not_breaking_into_unhandled_exceptions(self):
        filename = TEST_FILES.resolve('unhandled_exceptions_launch.py')
        cwd = os.path.dirname(filename)
        argv = ['localhost', str(PORT)]
        self.run_test_not_breaking_into_unhandled_exceptions(
            DebugInfo(
                filename=filename,
                cwd=cwd,
                starttype='attach',
                argv=argv,
            ))

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
            ), filename)

    def test_breaking_into_unhandled_exceptions(self):
        filename = TEST_FILES.resolve('unhandled_exceptions_launch.py')
        cwd = os.path.dirname(filename)
        argv = ['localhost', str(PORT)]
        self.run_test_breaking_into_unhandled_exceptions(
            DebugInfo(
                filename=filename,
                cwd=cwd,
                starttype='attach',
                argv=argv,
            ), filename)

    def test_breaking_into_raised_exceptions_only(self):
        filename = TEST_FILES.resolve('unhandled_exceptions_launch.py')
        cwd = os.path.dirname(filename)
        argv = ['localhost', str(PORT)]
        self.run_test_breaking_into_raised_exceptions_only(
            DebugInfo(
                filename=filename,
                cwd=cwd,
                starttype='attach',
                argv=argv,
            ), filename)

    def test_breaking_into_raised_and_unhandled_exceptions(self):
        filename = TEST_FILES.resolve('unhandled_exceptions_launch.py')
        cwd = os.path.dirname(filename)
        argv = ['localhost', str(PORT)]
        self.run_test_breaking_into_raised_and_unhandled_exceptions(
            DebugInfo(
                filename=filename,
                cwd=cwd,
                starttype='attach',
                argv=argv,
            ), filename)


class PTVSDAttachExceptionLifecycleTests(ExceptionTests):
    @unittest.skip('Needs fixing in #609, #580')
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

    @unittest.skip('Needs fixing in #609, #580')
    def test_not_breaking_into_unhandled_exceptions(self):
        filename = TEST_FILES.resolve('unhandled_exceptions_attach.py')
        cwd = os.path.dirname(filename)
        argv = ['localhost', str(PORT)]
        self.run_test_not_breaking_into_unhandled_exceptions(
            DebugInfo(
                filename=filename,
                attachtype='import',
                cwd=cwd,
                starttype='attach',
                argv=argv,
            ))

    @unittest.skip('#686')
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
            ), filename)

    def test_breaking_into_unhandled_exceptions(self):
        filename = TEST_FILES.resolve('unhandled_exceptions_attach.py')
        cwd = os.path.dirname(filename)
        argv = ['localhost', str(PORT)]
        self.run_test_breaking_into_unhandled_exceptions(
            DebugInfo(
                filename=filename,
                attachtype='import',
                cwd=cwd,
                starttype='attach',
                argv=argv,
            ), filename)

    @unittest.skip('Needs fixing in #609')
    def test_breaking_into_raised_exceptions_only(self):
        filename = TEST_FILES.resolve('unhandled_exceptions_attach.py')
        cwd = os.path.dirname(filename)
        argv = ['localhost', str(PORT)]
        self.run_test_breaking_into_raised_exceptions_only(
            DebugInfo(
                filename=filename,
                attachtype='import',
                cwd=cwd,
                starttype='attach',
                argv=argv,
            ), filename)

    @unittest.skip('Needs fixing in #609')
    def test_breaking_into_raised_and_unhandled_exceptions(self):
        filename = TEST_FILES.resolve('unhandled_exceptions_attach.py')
        cwd = os.path.dirname(filename)
        argv = ['localhost', str(PORT)]
        self.run_test_breaking_into_raised_and_unhandled_exceptions(
            DebugInfo(
                filename=filename,
                attachtype='import',
                cwd=cwd,
                starttype='attach',
                argv=argv,
            ), filename)


class ServerAttachModuleExceptionLifecycleTests(ExceptionTests):
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

    def test_not_breaking_into_unhandled_exceptions(self):
        module_name = 'mypkg_launch_unhandled'
        env = TEST_FILES.env_with_py_path()
        cwd = TEST_FILES.root
        argv = ['localhost', str(PORT)]
        self.run_test_not_breaking_into_unhandled_exceptions(
            DebugInfo(
                modulename=module_name,
                env=env,
                cwd=cwd,
                argv=argv,
                starttype='attach',
            ))

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
            ), os.path.join(TEST_FILES.root, module_name, '__init__.py'))

    def test_breaking_into_unhandled_exceptions(self):
        module_name = 'mypkg_launch_unhandled'
        env = TEST_FILES.env_with_py_path()
        cwd = TEST_FILES.root
        argv = ['localhost', str(PORT)]
        self.run_test_breaking_into_unhandled_exceptions(
            DebugInfo(
                modulename=module_name,
                env=env,
                cwd=cwd,
                argv=argv,
                starttype='attach',
            ),
            os.path.join(TEST_FILES.root, module_name, '__main__.py'))

    def test_breaking_into_raised_exceptions_only(self):
        module_name = 'mypkg_launch_unhandled'
        env = TEST_FILES.env_with_py_path()
        cwd = TEST_FILES.root
        argv = ['localhost', str(PORT)]
        self.run_test_breaking_into_raised_exceptions_only(
            DebugInfo(
                modulename=module_name,
                env=env,
                cwd=cwd,
                argv=argv,
                starttype='attach',
            ),
            os.path.join(TEST_FILES.root, module_name, '__main__.py'))

    def test_breaking_into_raised_and_unhandled_exceptions(self):
        module_name = 'mypkg_launch_unhandled'
        env = TEST_FILES.env_with_py_path()
        cwd = TEST_FILES.root
        argv = ['localhost', str(PORT)]
        self.run_test_breaking_into_raised_and_unhandled_exceptions(
            DebugInfo(
                modulename=module_name,
                env=env,
                cwd=cwd,
                argv=argv,
                starttype='attach',
            ),
            os.path.join(TEST_FILES.root, module_name, '__main__.py'))


class PTVSDAttachModuleExceptionLifecycleTests(ExceptionTests):
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

    def test_not_breaking_into_unhandled_exceptions(self):
        module_name = 'mypkg_attach_unhandled'
        env = TEST_FILES.env_with_py_path()
        cwd = TEST_FILES.root
        argv = ['localhost', str(PORT)]
        self.run_test_not_breaking_into_unhandled_exceptions(
            DebugInfo(
                modulename=module_name,
                env=env,
                cwd=cwd,
                argv=argv,
                attachtype='import',
                starttype='attach',
            ))

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
            ), os.path.join(TEST_FILES.root, module_name, '__init__.py'))

    def test_breaking_into_unhandled_exceptions(self):
        module_name = 'mypkg_attach_unhandled'
        env = TEST_FILES.env_with_py_path()
        cwd = TEST_FILES.root
        argv = ['localhost', str(PORT)]
        self.run_test_breaking_into_unhandled_exceptions(
            DebugInfo(
                modulename=module_name,
                env=env,
                cwd=cwd,
                argv=argv,
                attachtype='import',
                starttype='attach',
            ),
            os.path.join(TEST_FILES.root, module_name, '__main__.py'))

    @unittest.skip('To be fixed #724')
    def test_breaking_into_raised_exceptions_only(self):
        module_name = 'mypkg_attach_unhandled'
        env = TEST_FILES.env_with_py_path()
        cwd = TEST_FILES.root
        argv = ['localhost', str(PORT)]
        self.run_test_breaking_into_raised_exceptions_only(
            DebugInfo(
                modulename=module_name,
                env=env,
                cwd=cwd,
                argv=argv,
                attachtype='import',
                starttype='attach',
            ),
            os.path.join(TEST_FILES.root, module_name, '__main__.py'))

    @unittest.skip('To be fixed #723')
    def test_breaking_into_raised_and_unhandled_exceptions(self):
        module_name = 'mypkg_attach_unhandled'
        env = TEST_FILES.env_with_py_path()
        cwd = TEST_FILES.root
        argv = ['localhost', str(PORT)]
        self.run_test_breaking_into_raised_and_unhandled_exceptions(
            DebugInfo(
                modulename=module_name,
                env=env,
                cwd=cwd,
                argv=argv,
                attachtype='import',
                starttype='attach',
            ),
            os.path.join(TEST_FILES.root, module_name, '__main__.py'))
