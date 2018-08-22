import os
import os.path
import re
import threading
import time

from tests.helpers.resource import TestResources
from tests.helpers.webhelper import get_web_string_no_error
from . import (
    _strip_newline_output_events, lifecycle_handshake,
    LifecycleTestsBase, DebugInfo, PORT
)


TEST_FILES = TestResources.from_module(__name__)
re_link = r"(http(s|)\:\/\/[\w\.]*\:[0-9]{4,6}(\/|))"


class WebFrameworkTests(LifecycleTestsBase):
    def _get_url_from_output(self, session):
        strings = (e.body['output'] for e in
                   self.find_events(session.received, 'output'))
        for s in strings:
            matches = re.findall(re_link, s)
            if matches and matches[0]and matches[0][0].strip():
                return matches[0][0]
        return None

    def _wait_for_server_url(self, session):
        # wait for web server start by looking for
        # server url
        for _ in range(10):
            try:
                # wait for an output event.
                session.get_awaiter_for_event('output').wait(timeout=3.0)
                path = self._get_url_from_output(session)
                if path is not None:
                    return path
            except TimeoutError:
                pass
        return self._get_url_from_output(session)

    def run_test_with_break_points(self, debug_info, **kwargs):
        bp_filename = kwargs.pop('bp_filename')
        bp_line = kwargs.pop('bp_line')
        bp_name = kwargs.pop('bp_name')
        bp_var_value = kwargs.pop('bp_var_value')
        framework = kwargs.pop('framework', 'Django')
        if (debug_info.starttype == 'attach'):
            pathMappings = []
            pathMappings.append({
                'localRoot': debug_info.cwd,
                'remoteRoot': debug_info.cwd
            })
            options = {
                'debugOptions': ['RedirectOutput', framework],
                'pathMappings': pathMappings
                }
        else:
            options = {'debugOptions': ['RedirectOutput', framework]}

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

            stopped = session.get_awaiter_for_event(
                'stopped',
                condition=lambda msg: msg.body['reason'] == 'breakpoint')
            (_, req_launch_attach, _, _, _, _,
             ) = lifecycle_handshake(session, debug_info.starttype,
                                     options=options,
                                     breakpoints=breakpoints)
            req_launch_attach.wait()

            path = self._wait_for_server_url(session)
            # Give web server some time for finish writing output
            time.sleep(1)

            # connect to web server
            web_result = {}
            web_client_thread = threading.Thread(
                target=get_web_string_no_error,
                args=(path, web_result),
                name='test.webClient'
            )

            web_client_thread.start()

            stopped.wait(timeout=5.0)
            tid = stopped.event.body['threadId']

            req_stacktrace = session.send_request(
                'stackTrace',
                threadId=tid,
            )
            req_stacktrace.wait()
            stacktrace = req_stacktrace.resp.body

            frame_id = stacktrace['stackFrames'][0]['id']
            req_scopes = session.send_request(
                'scopes',
                frameId=frame_id,
            )
            req_scopes.wait()
            scopes = req_scopes.resp.body['scopes']
            variables_reference = scopes[0]['variablesReference']
            req_variables = session.send_request(
                'variables',
                variablesReference=variables_reference,
            )
            req_variables.wait()
            variables = req_variables.resp.body['variables']

            continued = session.get_awaiter_for_event('continued')
            session.send_request(
                'continue',
                threadId=tid,
            )
            continued.wait(timeout=3.0)

            # wait for flask rendering thread to exit
            web_client_thread.join(timeout=0.1)

            # shutdown to web server
            path += 'exit' if path.endswith('/') else '/exit'
            web_client_thread = threading.Thread(
                target=get_web_string_no_error,
                args=(path, None),
                name='test.webClient.shutdown'
            )
            web_client_thread.start()
            web_client_thread.join(timeout=1)

        received = list(_strip_newline_output_events(session.received))

        self.assertGreaterEqual(stacktrace['totalFrames'], 1)
        self.assert_is_subset(stacktrace, {
            # We get Python and PTVSD frames as well.
            # 'totalFrames': 2,
            'stackFrames': [{
                'id': 1,
                'name': bp_name,
                'source': {
                    'sourceReference': 0,
                    'path': bp_filename
                },
                'line': bp_line,
                'column': 1,
            }],
        })
        variables = list(v for v in variables if v['name'] == 'content')
        self.assert_is_subset(variables, [{
            'name': 'content',
            'type': 'str',
            'value': repr(bp_var_value),
            'presentationHint': {'attributes': ['rawString']},
            'evaluateName': 'content'
        }])
        self.assertTrue(web_result['content'].find(bp_var_value) != -1)
        self.assert_contains(received, [
            self.new_event(
                'stopped',
                reason='breakpoint',
                threadId=tid,
                text=None,
                description=None,
            ),
            self.new_event('continued', threadId=tid),
        ])

        if framework != 'Django':
            # TODO: Figure out better way to shutdown Django
            self.assert_contains(received, [
                self.new_event('exited', exitCode=0),
                self.new_event('terminated'),
            ])

    def run_test_with_handled_exception(self, debug_info, framework,
                                        expected_source_name):
        if (debug_info.starttype == 'attach'):
            pathMappings = []
            pathMappings.append({
                'localRoot': debug_info.cwd,
                'remoteRoot': debug_info.cwd
            })
            options = {
                'debugOptions': ['RedirectOutput', framework],
                'pathMappings': pathMappings
                }
        else:
            options = {'debugOptions': ['RedirectOutput', framework]}

        excbreakpoints = [{'filters': ['raised', 'uncaught']}]
        with self.start_debugging(debug_info) as dbg:
            session = dbg.session

            stopped = session.get_awaiter_for_event('stopped')
            (_, req_launch_attach, _, _, _, _,
             ) = lifecycle_handshake(session, debug_info.starttype,
                                     options=options,
                                     excbreakpoints=excbreakpoints)
            req_launch_attach.wait()

            base_path = self._wait_for_server_url(session)
            # Give web server some time for finish writing output
            time.sleep(1)

            # connect to web server
            path = base_path + \
                'handled' if base_path.endswith('/') else '/handled'
            web_result = {}
            web_client_thread = threading.Thread(
                target=get_web_string_no_error,
                args=(path, web_result),
                name='test.webClient'
            )

            web_client_thread.start()

            stopped.wait(timeout=5.0)
            thread_id = stopped.event.body['threadId']

            req_exc_info = session.send_request(
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

            continued = session.get_awaiter_for_event('continued')
            session.send_request(
                'continue',
                threadId=thread_id,
            )
            continued.wait(timeout=3.0)

            # Shutdown webserver
            path = base_path + 'exit' if base_path.endswith('/') else '/exit'
            web_client_thread = threading.Thread(
                target=get_web_string_no_error,
                args=(path, None),
                name='test.webClient.shutdown'
            )
            web_client_thread.start()
            web_client_thread.join(timeout=1)

        received = list(_strip_newline_output_events(dbg.session.received))
        if framework != 'Django':
            # TODO: Figure out better way to shutdown Django
            self.assert_contains(received, [
                self.new_event('exited', exitCode=0),
                self.new_event('terminated'),
            ])

    def run_test_with_unhandled_exception(self, debug_info, framework,
                                          expected_source_name):
        if (debug_info.starttype == 'attach'):
            pathMappings = []
            pathMappings.append({
                'localRoot': debug_info.cwd,
                'remoteRoot': debug_info.cwd
            })
            options = {
                'debugOptions': ['RedirectOutput', framework],
                'pathMappings': pathMappings
                }
        else:
            options = {'debugOptions': ['RedirectOutput', framework]}

        excbreakpoints = [{'filters': ['raised', 'uncaught']}]
        with self.start_debugging(debug_info) as dbg:
            session = dbg.session

            stopped = session.get_awaiter_for_event('stopped')
            (_, req_launch_attach, _, _, _, _,
             ) = lifecycle_handshake(session, debug_info.starttype,
                                     options=options,
                                     excbreakpoints=excbreakpoints)
            req_launch_attach.wait()

            base_path = self._wait_for_server_url(session)
            # Give web server some time for finish writing output
            time.sleep(1)

            # connect to web server
            path = base_path + \
                'unhandled' if base_path.endswith('/') else '/unhandled'
            web_result = {}
            web_client_thread = threading.Thread(
                target=get_web_string_no_error,
                args=(path, web_result),
                name='test.webClient'
            )

            web_client_thread.start()

            stopped.wait(timeout=5.0)
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

            continued = session.get_awaiter_for_event('continued')
            session.send_request(
                'continue',
                threadId=thread_id,
            )
            continued.wait(timeout=3.0)

            # Shutdown webserver
            path = base_path + 'exit' if base_path.endswith('/') else '/exit'
            web_client_thread = threading.Thread(
                target=get_web_string_no_error,
                args=(path, None),
                name='test.webClient.shutdown'
            )
            web_client_thread.start()
            web_client_thread.join(timeout=1)

        received = list(_strip_newline_output_events(dbg.session.received))
        if framework != 'Django':
            # TODO: Figure out better way to shutdown Django
            self.assert_contains(received, [
                self.new_event('exited', exitCode=0),
                self.new_event('terminated'),
            ])


class FlaskLaunchTests(WebFrameworkTests):
    def test_with_route_break_points(self):
        filename = TEST_FILES.resolve('flask', 'launch', 'app.py')
        cwd = os.path.dirname(filename)
        self.run_test_with_break_points(
            DebugInfo(
                modulename='flask',
                argv=['run', '--no-debugger', '--no-reload', '--with-threads'],
                env={
                    'FLASK_APP': 'app.py',
                    'FLASK_ENV': 'development',
                    'FLASK_DEBUG': '0',
                    'LC_ALL': 'C.UTF-8',
                    'LANG': 'C.UTF-8',
                },
                cwd=cwd),
            framework='Jinja',
            bp_filename=filename, bp_line=11, bp_name='home',
            bp_var_value='Flask-Jinja-Test')

    def test_with_template_break_points(self):
        filename = TEST_FILES.resolve('flask', 'launch', 'app.py')
        template = TEST_FILES.resolve(
            'flask', 'launch', 'templates', 'hello.html')
        cwd = os.path.dirname(filename)
        self.run_test_with_break_points(
            DebugInfo(
                modulename='flask',
                argv=['run', '--no-debugger', '--no-reload', '--with-threads'],
                env={
                    'FLASK_APP': 'app.py',
                    'FLASK_ENV': 'development',
                    'FLASK_DEBUG': '0',
                    'LC_ALL': 'C.UTF-8',
                    'LANG': 'C.UTF-8',
                },
                cwd=cwd),
            framework='Jinja',
            bp_filename=template, bp_line=8, bp_name='template',
            bp_var_value='Flask-Jinja-Test')

    def test_with_handled_exceptions(self):
        filename = TEST_FILES.resolve('flask', 'launch', 'app.py')
        cwd = os.path.dirname(filename)
        self.run_test_with_handled_exception(
            DebugInfo(
                modulename='flask',
                argv=['run', '--no-debugger', '--no-reload', '--with-threads'],
                env={
                    'FLASK_APP': 'app.py',
                    'FLASK_ENV': 'development',
                    'FLASK_DEBUG': '0',
                    'LC_ALL': 'C.UTF-8',
                    'LANG': 'C.UTF-8',
                },
                cwd=cwd), 'Jinja', filename)

    def test_with_unhandled_exceptions(self):
        filename = TEST_FILES.resolve('flask', 'launch', 'app.py')
        cwd = os.path.dirname(filename)
        self.run_test_with_unhandled_exception(
            DebugInfo(
                modulename='flask',
                argv=['run', '--no-debugger', '--no-reload', '--with-threads'],
                env={
                    'FLASK_APP': 'app.py',
                    'FLASK_ENV': 'development',
                    'FLASK_DEBUG': '0',
                    'LC_ALL': 'C.UTF-8',
                    'LANG': 'C.UTF-8',
                },
                cwd=cwd), 'Jinja', filename)


class FlaskAttachTests(WebFrameworkTests):
    def test_with_route_break_points(self):
        filename = TEST_FILES.resolve('flask', 'attach', 'app.py')
        cwd = os.path.dirname(filename)
        self.run_test_with_break_points(
            DebugInfo(
                starttype='attach',
                modulename='flask',
                argv=['run', '--no-debugger', '--no-reload', '--with-threads'],
                env={
                    'FLASK_APP': 'app.py',
                    'FLASK_ENV': 'development',
                    'FLASK_DEBUG': '0',
                    'LC_ALL': 'C.UTF-8',
                    'LANG': 'C.UTF-8',
                    'PTVSD_HOST': 'localhost',
                    'PTVSD_PORT': str(PORT),
                },
                cwd=cwd),
            framework='Jinja',
            bp_filename=filename, bp_line=19, bp_name='home',
            bp_var_value='Flask-Jinja-Test')

    def test_with_template_break_points(self):
        filename = TEST_FILES.resolve('flask', 'attach', 'app.py')
        template = TEST_FILES.resolve(
            'flask', 'attach', 'templates', 'hello.html')
        cwd = os.path.dirname(filename)
        self.run_test_with_break_points(
            DebugInfo(
                starttype='attach',
                modulename='flask',
                argv=['run', '--no-debugger', '--no-reload', '--with-threads'],
                env={
                    'FLASK_APP': 'app.py',
                    'FLASK_ENV': 'production',
                    'LC_ALL': 'C.UTF-8',
                    'LANG': 'C.UTF-8',
                    'PTVSD_HOST': 'localhost',
                    'PTVSD_PORT': str(PORT),
                },
                cwd=cwd),
            framework='Jinja',
            bp_filename=template, bp_line=8, bp_name='template',
            bp_var_value='Flask-Jinja-Test')

    def test_with_handled_exceptions(self):
        filename = TEST_FILES.resolve('flask', 'attach', 'app.py')
        cwd = os.path.dirname(filename)
        self.run_test_with_handled_exception(
            DebugInfo(
                starttype='attach',
                modulename='flask',
                argv=['run', '--no-debugger', '--no-reload', '--with-threads'],
                env={
                    'FLASK_APP': 'app.py',
                    'FLASK_ENV': 'production',
                    'LC_ALL': 'C.UTF-8',
                    'LANG': 'C.UTF-8',
                    'PTVSD_HOST': 'localhost',
                    'PTVSD_PORT': str(PORT),
                },
                cwd=cwd), 'Jinja', filename)

    def test_with_unhandled_exceptions(self):
        filename = TEST_FILES.resolve('flask', 'attach', 'app.py')
        cwd = os.path.dirname(filename)
        self.run_test_with_unhandled_exception(
            DebugInfo(
                starttype='attach',
                modulename='flask',
                argv=['run', '--no-debugger', '--no-reload', '--with-threads'],
                env={
                    'FLASK_APP': 'app.py',
                    'FLASK_ENV': 'production',
                    'LC_ALL': 'C.UTF-8',
                    'LANG': 'C.UTF-8',
                    'PTVSD_HOST': 'localhost',
                    'PTVSD_PORT': str(PORT),
                },
                cwd=cwd), 'Jinja', filename)


class DjangoLaunchTests(WebFrameworkTests):
    def test_with_route_break_points(self):
        filename = TEST_FILES.resolve('django', 'launch', 'app.py')
        cwd = os.path.dirname(filename)
        self.run_test_with_break_points(
            DebugInfo(
                filename=filename,
                argv=['runserver', '--noreload', '--nothreading'],
                cwd=cwd),
            framework='Django',
            bp_filename=filename, bp_line=40, bp_name='home',
            bp_var_value='Django-Django-Test')

    def test_with_template_break_points(self):
        filename = TEST_FILES.resolve('django', 'launch', 'app.py')
        template = TEST_FILES.resolve(
            'django', 'launch', 'templates', 'hello.html')
        cwd = os.path.dirname(filename)
        self.run_test_with_break_points(
            DebugInfo(
                filename=filename,
                argv=['runserver', '--noreload', '--nothreading'],
                cwd=cwd),
            framework='Django',
            bp_filename=template, bp_line=8, bp_name='Django Template',
            bp_var_value='Django-Django-Test')

    def test_with_handled_exceptions(self):
        filename = TEST_FILES.resolve('django', 'launch', 'app.py')
        cwd = os.path.dirname(filename)
        self.run_test_with_handled_exception(
            DebugInfo(
                filename=filename,
                argv=['runserver', '--noreload', '--nothreading'],
                cwd=cwd), 'Django', filename)

    def test_with_unhandled_exceptions(self):
        filename = TEST_FILES.resolve('django', 'launch', 'app.py')
        cwd = os.path.dirname(filename)
        self.run_test_with_unhandled_exception(
            DebugInfo(
                filename=filename,
                argv=['runserver', '--noreload', '--nothreading'],
                cwd=cwd), 'Django', filename)


class DjangoAttachTests(WebFrameworkTests):
    def test_with_route_break_points(self):
        filename = TEST_FILES.resolve('django', 'attach', 'app.py')
        cwd = os.path.dirname(filename)
        self.run_test_with_break_points(
            DebugInfo(
                filename=filename,
                starttype='attach',
                argv=['runserver', '--noreload', '--nothreading'],
                env={
                    'PTVSD_HOST': 'localhost',
                    'PTVSD_PORT': str(PORT),
                },
                cwd=cwd),
            framework='Django',
            bp_filename=filename, bp_line=47, bp_name='home',
            bp_var_value='Django-Django-Test')

    def test_with_template_break_points(self):
        filename = TEST_FILES.resolve('django', 'attach', 'app.py')
        template = TEST_FILES.resolve(
            'django', 'attach', 'templates', 'hello.html')
        cwd = os.path.dirname(filename)
        self.run_test_with_break_points(
            DebugInfo(
                filename=filename,
                starttype='attach',
                argv=['runserver', '--noreload', '--nothreading'],
                env={
                    'PTVSD_HOST': 'localhost',
                    'PTVSD_PORT': str(PORT),
                },
                cwd=cwd),
            framework='Django',
            bp_filename=template, bp_line=8, bp_name='Django Template',
            bp_var_value='Django-Django-Test')

    def test_with_handled_exceptions(self):
        filename = TEST_FILES.resolve('django', 'attach', 'app.py')
        cwd = os.path.dirname(filename)
        self.run_test_with_handled_exception(
            DebugInfo(
                filename=filename,
                starttype='attach',
                argv=['runserver', '--noreload', '--nothreading'],
                env={
                    'PTVSD_HOST': 'localhost',
                    'PTVSD_PORT': str(PORT),
                },
                cwd=cwd), 'Django', filename)

    def test_with_unhandled_exceptions(self):
        filename = TEST_FILES.resolve('django', 'attach', 'app.py')
        cwd = os.path.dirname(filename)
        self.run_test_with_unhandled_exception(
            DebugInfo(
                filename=filename,
                starttype='attach',
                argv=['runserver', '--noreload', '--nothreading'],
                env={
                    'PTVSD_HOST': 'localhost',
                    'PTVSD_PORT': str(PORT),
                },
                cwd=cwd), 'Django', filename)
