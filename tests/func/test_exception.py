# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

import pytest

from tests.helpers import print
from tests.helpers.session import DebugSession
from tests.helpers.timeline import Event
from tests.helpers.pattern import ANY, Path


@pytest.mark.parametrize('raised', ['raisedOn', 'raisedOff'])
@pytest.mark.parametrize('uncaught', ['uncaughtOn', 'uncaughtOff'])
def test_vsc_exception_options_raise_with_except(pyfile, run_as, start_method, raised, uncaught):
    @pyfile
    def code_to_debug():
        from dbgimporter import import_and_enable_debugger
        import_and_enable_debugger()
        def raise_with_except():
            try:
                raise ArithmeticError('bad code')
            except Exception:
                pass
        raise_with_except()

    ex_line = 5
    filters = []
    filters += ['raised'] if raised == 'raisedOn' else []
    filters += ['uncaught'] if uncaught == 'uncaughtOn' else []
    with DebugSession() as session:
        session.initialize(
            target=(run_as, code_to_debug),
            start_method=start_method,
            ignore_unobserved=[Event('continued')],
        )
        session.send_request('setExceptionBreakpoints', {
            'filters': filters
        }).wait_for_response()
        session.start_debugging()

        expected = ANY.dict_with({
            'exceptionId': ANY.such_that(lambda s: s.endswith('ArithmeticError')),
            'description': 'bad code',
            'breakMode': 'always' if raised == 'raisedOn' else 'unhandled',
            'details': ANY.dict_with({
                'typeName': ANY.such_that(lambda s: s.endswith('ArithmeticError')),
                'message': 'bad code',
                'source': Path(code_to_debug),
            }),
        })

        if raised == 'raisedOn':
            hit = session.wait_for_thread_stopped(reason='exception')
            frames = hit.stacktrace.body['stackFrames']
            assert ex_line == frames[0]['line']

            resp_exc_info = session.send_request('exceptionInfo', {
                'threadId': hit.thread_id
            }).wait_for_response()

            assert resp_exc_info.body == expected
            session.send_request('continue').wait_for_response(freeze=False)

        # uncaught should not 'stop' matter since the exception is caught

        session.wait_for_exit()


@pytest.mark.parametrize('raised', ['raisedOn', 'raisedOff'])
@pytest.mark.parametrize('uncaught', ['uncaughtOn', 'uncaughtOff'])
def test_vsc_exception_options_raise_without_except(pyfile, run_as, start_method, raised, uncaught):
    @pyfile
    def code_to_debug():
        from dbgimporter import import_and_enable_debugger
        import_and_enable_debugger()
        def raise_without_except():
            raise ArithmeticError('bad code')
        raise_without_except()

    ex_line = 4
    filters = []
    filters += ['raised'] if raised == 'raisedOn' else []
    filters += ['uncaught'] if uncaught == 'uncaughtOn' else []
    with DebugSession() as session:
        session.initialize(
            target=(run_as, code_to_debug),
            start_method=start_method,
            ignore_unobserved=[Event('continued'), Event('stopped')],
            expected_returncode=ANY.int,
        )
        session.send_request('setExceptionBreakpoints', {
            'filters': filters
        }).wait_for_response()
        session.start_debugging()

        expected = ANY.dict_with({
            'exceptionId': ANY.such_that(lambda s: s.endswith('ArithmeticError')),
            'description': 'bad code',
            'breakMode': 'always' if raised == 'raisedOn' else 'unhandled',
            'details': ANY.dict_with({
                'typeName': ANY.such_that(lambda s: s.endswith('ArithmeticError')),
                'message': 'bad code',
                'source': Path(code_to_debug),
            }),
        })

        if raised == 'raisedOn':
            hit = session.wait_for_thread_stopped(reason='exception')
            frames = hit.stacktrace.body['stackFrames']
            assert ex_line == frames[0]['line']

            resp_exc_info = session.send_request('exceptionInfo', {
                'threadId': hit.thread_id
            }).wait_for_response()

            assert resp_exc_info.body == expected
            session.send_request('continue').wait_for_response(freeze=False)

            # NOTE: debugger stops at each frame if raised and is uncaught
            # This behavior can be changed by updating 'notify_on_handled_exceptions'
            # setting we send to pydevd to notify only once. In our test code, we have
            # two frames, hence two stops.
            session.wait_for_thread_stopped(reason='exception')
            session.send_request('continue').wait_for_response(freeze=False)

        if uncaught == 'uncaughtOn':
            hit = session.wait_for_thread_stopped(reason='exception')
            frames = hit.stacktrace.body['stackFrames']
            assert ex_line == frames[0]['line']

            resp_exc_info = session.send_request('exceptionInfo', {
                'threadId': hit.thread_id
            }).wait_for_response()

            assert resp_exc_info.body == expected
            session.send_request('continue').wait_for_response(freeze=False)

        session.wait_for_exit()


@pytest.mark.parametrize('raised', ['raised', ''])
@pytest.mark.parametrize('uncaught', ['uncaught', ''])
@pytest.mark.parametrize('zero', ['zero', ''])
@pytest.mark.parametrize('exit_code', [0, 1, 'nan'])
def test_systemexit(pyfile, run_as, start_method, raised, uncaught, zero, exit_code):
    @pyfile
    def code_to_debug():
        from dbgimporter import import_and_enable_debugger
        import_and_enable_debugger()
        import sys
        exit_code = eval(sys.argv[1])
        print('sys.exit(%r)' % (exit_code,))
        try:
            sys.exit(exit_code)
        except SystemExit:
            pass
        sys.exit(exit_code)

    filters = []
    if raised:
        filters += ['raised']
    if uncaught:
        filters += ['uncaught']

    with DebugSession() as session:
        session.program_args = [repr(exit_code)]
        if zero:
            session.debug_options += ['BreakOnSystemExitZero']
        session.initialize(
            target=(run_as, code_to_debug),
            start_method=start_method,
            ignore_unobserved=[Event('continued'), Event('stopped')],
            expected_returncode=ANY.int,
        )
        session.send_request('setExceptionBreakpoints', {
            'filters': filters
        }).wait_for_response()
        session.start_debugging()

        # When breaking on raised exceptions, we'll stop on both lines,
        # unless it's SystemExit(0) and we asked to ignore that.
        if raised and (zero or exit_code != 0):
            hit = session.wait_for_thread_stopped(reason='exception')
            frames = hit.stacktrace.body['stackFrames']
            assert frames[0]['line'] == 7
            session.send_request('continue').wait_for_response(freeze=False)

            hit = session.wait_for_thread_stopped(reason='exception')
            frames = hit.stacktrace.body['stackFrames']
            assert frames[0]['line'] == 10
            session.send_request('continue').wait_for_response(freeze=False)

        # When breaking on uncaught exceptions, we'll stop on the second line,
        # unless it's SystemExit(0) and we asked to ignore that.
        # Note that if both raised and uncaught filters are set, there will be
        # two stop for the second line - one for exception being raised, and one
        # for it unwinding the stack without finding a handler. The block above
        # takes care of the first stop, so here we just take care of the second.
        if uncaught and (zero or exit_code != 0):
            hit = session.wait_for_thread_stopped(reason='exception')
            frames = hit.stacktrace.body['stackFrames']
            assert frames[0]['line'] == 10
            session.send_request('continue').wait_for_response(freeze=False)

        session.wait_for_exit()
