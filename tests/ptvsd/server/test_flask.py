# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import platform
import pytest
import sys

from tests import debug, net, test_data
from tests.patterns import some
from tests.timeline import Event


FLASK1_ROOT = test_data / 'flask1'
FLASK1_APP = FLASK1_ROOT / 'app.py'
FLASK1_TEMPLATE = FLASK1_ROOT / 'templates' / 'hello.html'
FLASK1_BAD_TEMPLATE = FLASK1_ROOT / 'templates' / 'bad.html'
FLASK_PORT = net.get_test_server_port(7000, 7100)

flask_server = net.WebServer(FLASK_PORT)


def _initialize_flask_session_no_multiproc(session, start_method):
    env = {
        'FLASK_APP': 'app.py',
        'FLASK_ENV': 'development',
        'FLASK_DEBUG': '0',
    }
    if platform.system() != 'Windows':
        locale = 'en_US.utf8' if platform.system() == 'Linux' else 'en_US.UTF-8'
        env.update({
            'LC_ALL': locale,
            'LANG': locale,
        })

    session.initialize(
        start_method=start_method,
        target=('module', 'flask'),
        program_args=['run', '--no-debugger', '--no-reload', '--with-threads', '--port', str(FLASK_PORT)],
        ignore_unobserved=[Event('stopped')],
        debug_options=['Jinja'],
        cwd=FLASK1_ROOT,
        env=env,
        expected_returncode=ANY.int,  # No clean way to kill Flask server
    )


@pytest.mark.parametrize('bp_target', ['code', 'template'])
@pytest.mark.parametrize('start_method', ['launch', 'attach_socket_cmdline'])
@pytest.mark.timeout(60)
def test_flask_breakpoint_no_multiproc(bp_target, start_method):
    bp_file, bp_line, bp_name = {
        'code': (FLASK1_APP, 11, 'home'),
        'template': (FLASK1_TEMPLATE, 8, 'template')
    }[bp_target]

    with debug.Session() as session:
        _initialize_flask_session_no_multiproc(session, start_method)

        bp_var_content = 'Flask-Jinja-Test'
        session.set_breakpoints(bp_file, [bp_line])
        session.start_debugging()

        # wait for Flask web server to start
        wait_for_connection(FLASK_PORT)
        link = FLASK_LINK
        web_request = get_web_content(link, {})

        thread_stopped = session.wait_for_next(Event('stopped'), ANY.dict_with({'reason': 'breakpoint'}))
        assert thread_stopped.body['threadId'] is not None

        tid = thread_stopped.body['threadId']

        resp_stacktrace = session.send_request('stackTrace', arguments={
            'threadId': tid,
        }).wait_for_response()
        assert resp_stacktrace.body['totalFrames'] > 0
        frames = resp_stacktrace.body['stackFrames']
        assert frames[0] == {
            'id': ANY.dap_id,
            'name': bp_name,
            'source': {
                'sourceReference': ANY.dap_id,
                'path': Path(bp_file),
            },
            'line': bp_line,
            'column': 1,
        }

        fid = frames[0]['id']
        resp_scopes = session.send_request('scopes', arguments={
            'frameId': fid
        }).wait_for_response()
        scopes = resp_scopes.body['scopes']
        assert len(scopes) > 0

        resp_variables = session.send_request('variables', arguments={
            'variablesReference': scopes[0]['variablesReference']
        }).wait_for_response()
        variables = list(v for v in resp_variables.body['variables'] if v['name'] == 'content')
        assert variables == [{
                'name': 'content',
                'type': 'str',
                'value': repr(bp_var_content),
                'presentationHint': {'attributes': ['rawString']},
                'evaluateName': 'content',
                'variablesReference': 0,
            }]

        session.send_request('continue').wait_for_response(freeze=False)

        web_content = web_request.wait_for_response()
        assert web_content.find(bp_var_content) != -1

        # shutdown to web server
        link = FLASK_LINK + 'exit'
        get_web_content(link).wait_for_response()

        session.wait_for_exit()


@pytest.mark.parametrize('start_method', ['launch', 'attach_socket_cmdline'])
@pytest.mark.timeout(60)
def test_flask_template_exception_no_multiproc(start_method):
    with debug.Session() as session:
        _initialize_flask_session_no_multiproc(session, start_method)

        session.send_request('setExceptionBreakpoints', arguments={
            'filters': ['raised', 'uncaught'],
        }).wait_for_response()

        session.start_debugging()

        # wait for Flask web server to start
        wait_for_connection(FLASK_PORT)
        base_link = FLASK_LINK
        part = 'badtemplate'
        link = base_link + part if base_link.endswith('/') else ('/' + part)
        web_request = get_web_content(link, {})

        hit = session.wait_for_thread_stopped()
        frames = hit.stacktrace.body['stackFrames']
        assert frames[0] == ANY.dict_with({
            'id': ANY.dap_id,
            'name': 'template' if sys.version_info[0] >= 3 else 'Jinja2 TemplateSyntaxError',
            'source': ANY.dict_with({
                'sourceReference': ANY.dap_id,
                'path': Path(FLASK1_BAD_TEMPLATE),
            }),
            'line': 8,
            'column': 1,
        })

        resp_exception_info = session.send_request(
            'exceptionInfo',
            arguments={'threadId': hit.thread_id, }
        ).wait_for_response()
        exception = resp_exception_info.body
        assert exception == ANY.dict_with({
            'exceptionId': ANY.such_that(lambda s: s.endswith('TemplateSyntaxError')),
            'breakMode': 'always',
            'description': ANY.such_that(lambda s: s.find('doesnotexist') > -1),
            'details': ANY.dict_with({
                'message': ANY.such_that(lambda s: s.find('doesnotexist') > -1),
                'typeName': ANY.such_that(lambda s: s.endswith('TemplateSyntaxError')),
            })
        })

        session.send_request('continue').wait_for_response(freeze=False)

        # ignore response for exception tests
        web_request.wait_for_response()

        # shutdown to web server
        link = base_link + 'exit' if base_link.endswith('/') else '/exit'
        get_web_content(link).wait_for_response()

        session.wait_for_exit()


@pytest.mark.parametrize('ex_type', ['handled', 'unhandled'])
@pytest.mark.parametrize('start_method', ['launch', 'attach_socket_cmdline'])
@pytest.mark.timeout(60)
def test_flask_exception_no_multiproc(ex_type, start_method):
    ex_line = {
        'handled': 21,
        'unhandled': 33,
    }[ex_type]

    with debug.Session() as session:
        _initialize_flask_session_no_multiproc(session, start_method)

        session.send_request('setExceptionBreakpoints', arguments={
            'filters': ['raised', 'uncaught'],
        }).wait_for_response()

        session.start_debugging()

        # wait for Flask web server to start
        wait_for_connection(FLASK_PORT)
        base_link = FLASK_LINK
        link = base_link + ex_type if base_link.endswith('/') else ('/' + ex_type)
        web_request = get_web_content(link, {})

        thread_stopped = session.wait_for_next(Event('stopped', ANY.dict_with({'reason': 'exception'})))
        assert thread_stopped == Event('stopped', ANY.dict_with({
            'reason': 'exception',
            'text': ANY.such_that(lambda s: s.endswith('ArithmeticError')),
            'description': 'Hello'
        }))

        tid = thread_stopped.body['threadId']
        resp_exception_info = session.send_request(
            'exceptionInfo',
            arguments={'threadId': tid, }
        ).wait_for_response()
        exception = resp_exception_info.body
        assert exception == {
            'exceptionId': ANY.such_that(lambda s: s.endswith('ArithmeticError')),
            'breakMode': 'always',
            'description': 'Hello',
            'details': {
                'message': 'Hello',
                'typeName': ANY.such_that(lambda s: s.endswith('ArithmeticError')),
                'source': Path(FLASK1_APP),
                'stackTrace': ANY.such_that(lambda s: True)
            }
        }

        resp_stacktrace = session.send_request('stackTrace', arguments={
            'threadId': tid,
        }).wait_for_response()
        assert resp_stacktrace.body['totalFrames'] > 0
        frames = resp_stacktrace.body['stackFrames']
        assert frames[0] == {
            'id': ANY.dap_id,
            'name': 'bad_route_' + ex_type,
            'source': {
                'sourceReference': ANY.dap_id,
                'path': Path(FLASK1_APP),
            },
            'line': ex_line,
            'column': 1,
        }

        session.send_request('continue').wait_for_response(freeze=False)

        # ignore response for exception tests
        web_request.wait_for_response()

        # shutdown to web server
        link = base_link + 'exit' if base_link.endswith('/') else '/exit'
        get_web_content(link).wait_for_response()

        session.wait_for_exit()


@pytest.mark.timeout(120)
@pytest.mark.parametrize('start_method', ['launch'])
@pytest.mark.skipif((sys.version_info < (3, 0)) and (platform.system() != 'Windows'), reason='Bug #935')
def test_flask_breakpoint_multiproc(start_method):
    env = {
        'FLASK_APP': 'app',
        'FLASK_ENV': 'development',
        'FLASK_DEBUG': '1',
    }
    if platform.system() != 'Windows':
        locale = 'en_US.utf8' if platform.system() == 'Linux' else 'en_US.UTF-8'
        env.update({
            'LC_ALL': locale,
            'LANG': locale,
        })

    with debug.Session() as parent_session:
        parent_session.initialize(
            start_method=start_method,
            target=('module', 'flask'),
            multiprocess=True,
            program_args=['run', '--port', str(FLASK_PORT)],
            ignore_unobserved=[Event('stopped')],
            debug_options=['Jinja'],
            cwd=FLASK1_ROOT,
            env=env,
            expected_returncode=ANY.int,  # No clean way to kill Flask server
        )

        bp_line = 11
        bp_var_content = 'Flask-Jinja-Test'
        parent_session.set_breakpoints(FLASK1_APP, [bp_line])
        parent_session.start_debugging()

        with parent_session.connect_to_next_child_session() as child_session:
            child_session.send_request('setBreakpoints', arguments={
                'source': {'path': FLASK1_APP},
                'breakpoints': [{'line': bp_line}, ],
            }).wait_for_response()
            child_session.start_debugging()

            # wait for Flask server to start
            wait_for_connection(FLASK_PORT)
            web_request = get_web_content(FLASK_LINK, {})

            thread_stopped = child_session.wait_for_next(Event('stopped', ANY.dict_with({'reason': 'breakpoint'})))
            assert thread_stopped.body['threadId'] is not None

            tid = thread_stopped.body['threadId']

            resp_stacktrace = child_session.send_request('stackTrace', arguments={
                'threadId': tid,
            }).wait_for_response()
            assert resp_stacktrace.body['totalFrames'] > 0
            frames = resp_stacktrace.body['stackFrames']
            assert frames[0] == {
                'id': ANY.dap_id,
                'name': 'home',
                'source': {
                    'sourceReference': ANY.dap_id,
                    'path': Path(FLASK1_APP),
                },
                'line': bp_line,
                'column': 1,
            }

            fid = frames[0]['id']
            resp_scopes = child_session.send_request('scopes', arguments={
                'frameId': fid
            }).wait_for_response()
            scopes = resp_scopes.body['scopes']
            assert len(scopes) > 0

            resp_variables = child_session.send_request('variables', arguments={
                'variablesReference': scopes[0]['variablesReference']
            }).wait_for_response()
            variables = [v for v in resp_variables.body['variables'] if v['name'] == 'content']
            assert variables == [{
                    'name': 'content',
                    'type': 'str',
                    'value': repr(bp_var_content),
                    'presentationHint': {'attributes': ['rawString']},
                    'evaluateName': 'content',
                    'variablesReference': 0,
                }]

            child_session.send_request('continue').wait_for_response(freeze=False)

            web_content = web_request.wait_for_response()
            assert web_content.find(bp_var_content) != -1

            # shutdown to web server
            link = FLASK_LINK + 'exit'
            get_web_content(link).wait_for_response()

            child_session.wait_for_termination()
            parent_session.wait_for_exit()
