# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

import os.path
import platform
import pytest
import sys

import tests.helpers
from tests.helpers.pattern import ANY, Path
from tests.helpers.session import DebugSession
from tests.helpers.timeline import Event
from tests.helpers.webhelper import get_web_content, wait_for_connection
from tests.helpers.pathutils import get_test_root


FLASK1_ROOT = get_test_root('flask1')
FLASK1_APP = os.path.join(FLASK1_ROOT, 'app.py')
FLASK1_TEMPLATE = os.path.join(FLASK1_ROOT, 'templates', 'hello.html')
FLASK_PORT = tests.helpers.get_unique_port(5000)
FLASK_LINK = 'http://127.0.0.1:{}/'.format(FLASK_PORT)


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
        ignore_unobserved=[Event('stopped'), Event('continued')],
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

    with DebugSession() as session:
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
            'id': ANY.int,
            'name': bp_name,
            'source': {
                'sourceReference': ANY.int,
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
                'evaluateName': 'content'
            }]

        session.send_request('continue').wait_for_response(freeze=False)

        web_content = web_request.wait_for_response()
        assert web_content.find(bp_var_content) != -1

        # shutdown to web server
        link = FLASK_LINK + 'exit'
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

    with DebugSession() as session:
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
            'id': ANY.int,
            'name': 'bad_route_' + ex_type,
            'source': {
                'sourceReference': ANY.int,
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

    with DebugSession() as parent_session:
        parent_session.initialize(
            start_method=start_method,
            target=('module', 'flask'),
            multiprocess=True,
            program_args=['run', '--port', str(FLASK_PORT)],
            ignore_unobserved=[Event('stopped'), Event('continued')],
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
                'id': ANY.int,
                'name': 'home',
                'source': {
                    'sourceReference': ANY.int,
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
                    'evaluateName': 'content'
                }]

            child_session.send_request('continue').wait_for_response(freeze=False)

            web_content = web_request.wait_for_response()
            assert web_content.find(bp_var_content) != -1

            # shutdown to web server
            link = FLASK_LINK + 'exit'
            get_web_content(link).wait_for_response()

            child_session.wait_for_termination()
            parent_session.wait_for_exit()
