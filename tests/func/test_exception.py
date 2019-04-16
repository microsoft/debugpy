# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

import pytest

from tests.helpers import print, get_marked_line_numbers
from tests.helpers.session import DebugSession
from tests.helpers.timeline import Event
from tests.helpers.pattern import ANY, Path, Regex


@pytest.mark.parametrize('raised', ['raisedOn', 'raisedOff'])
@pytest.mark.parametrize('uncaught', ['uncaughtOn', 'uncaughtOff'])
def test_vsc_exception_options_raise_with_except(pyfile, run_as, start_method, raised, uncaught):

    @pyfile
    def code_to_debug():
        from dbgimporter import import_and_enable_debugger
        import_and_enable_debugger()

        def raise_with_except():
            try:
                raise ArithmeticError('bad code')  # @exception_line
            except Exception:
                pass

        raise_with_except()

    line_numbers = get_marked_line_numbers(code_to_debug)
    ex_line = line_numbers['exception_line']
    filters = []
    filters += ['raised'] if raised == 'raisedOn' else []
    filters += ['uncaught'] if uncaught == 'uncaughtOn' else []
    with DebugSession() as session:
        session.initialize(
            target=(run_as, code_to_debug),
            start_method=start_method,
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
            raise ArithmeticError('bad code')  # @exception_line

        raise_without_except()

    line_numbers = get_marked_line_numbers(code_to_debug)
    ex_line = line_numbers['exception_line']
    filters = []
    filters += ['raised'] if raised == 'raisedOn' else []
    filters += ['uncaught'] if uncaught == 'uncaughtOn' else []
    with DebugSession() as session:
        session.initialize(
            target=(run_as, code_to_debug),
            start_method=start_method,
            ignore_unobserved=[Event('stopped')],
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

            expected = ANY.dict_with({
                'exceptionId': ANY.such_that(lambda s: s.endswith('ArithmeticError')),
                'description': 'bad code',
                'breakMode': 'unhandled',  # Only difference from previous expected is breakMode.
                'details': ANY.dict_with({
                    'typeName': ANY.such_that(lambda s: s.endswith('ArithmeticError')),
                    'message': 'bad code',
                    'source': Path(code_to_debug),
                }),
            })

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
            sys.exit(exit_code)  # @handled
        except SystemExit:
            pass
        sys.exit(exit_code)  # @unhandled

    line_numbers = get_marked_line_numbers(code_to_debug)

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
            assert frames[0]['line'] == line_numbers['handled']
            session.send_request('continue').wait_for_response(freeze=False)

            hit = session.wait_for_thread_stopped(reason='exception')
            frames = hit.stacktrace.body['stackFrames']
            assert frames[0]['line'] == line_numbers['unhandled']
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
            assert frames[0]['line'] == line_numbers['unhandled']
            session.send_request('continue').wait_for_response(freeze=False)

        session.wait_for_exit()


@pytest.mark.parametrize('break_mode', ['always', 'never', 'unhandled', 'userUnhandled'])
@pytest.mark.parametrize('exceptions', [
    ['RuntimeError'],
    ['AssertionError'],
    ['RuntimeError', 'AssertionError'],
    [],  # Add the whole Python Exceptions category.
    ])
def test_raise_exception_options(pyfile, run_as, start_method, exceptions, break_mode):

    if break_mode in ('never', 'unhandled', 'userUnhandled'):

        @pyfile
        def code_to_debug():
            from dbgimporter import import_and_enable_debugger
            import_and_enable_debugger()
            raise AssertionError()  # @AssertionError

        if break_mode == 'never':
            expect_exceptions = []

        elif 'AssertionError' in exceptions or not exceptions:
            # Only AssertionError is raised in this use-case.
            expect_exceptions = ['AssertionError']

        else:
            expect_exceptions = []

    else:
        expect_exceptions = exceptions[:]
        if not expect_exceptions:
            # Deal with the Python Exceptions category
            expect_exceptions = ['RuntimeError', 'AssertionError', 'IndexError']

        @pyfile
        def code_to_debug():
            from dbgimporter import import_and_enable_debugger
            import_and_enable_debugger()
            try:
                raise RuntimeError()  # @RuntimeError
            except RuntimeError:
                pass
            try:
                raise AssertionError()  # @AssertionError
            except AssertionError:
                pass
            try:
                raise IndexError()  # @IndexError
            except IndexError:
                pass

    line_numbers = get_marked_line_numbers(code_to_debug)

    with DebugSession() as session:
        session.initialize(
            target=(run_as, code_to_debug),
            start_method=start_method,
            ignore_unobserved=[Event('stopped')],
            expected_returncode=ANY.int,
        )
        path = [
            {'names': ['Python Exceptions']},
        ]
        if exceptions:
            path.append({'names': exceptions})
        session.send_request('setExceptionBreakpoints', {
            'filters': [],  # Unused when exceptionOptions is passed.
            'exceptionOptions': [{
                'path': path,
                'breakMode': break_mode,  # Can be "never", "always", "unhandled", "userUnhandled"
            }],
        }).wait_for_response()
        session.start_debugging()

        for expected_exception in expect_exceptions:
            hit = session.wait_for_thread_stopped(reason='exception')
            frames = hit.stacktrace.body['stackFrames']
            assert frames[0]['source']['path'].endswith('code_to_debug.py')
            assert frames[0]['line'] == line_numbers[expected_exception]
            session.send_request('continue').wait_for_response(freeze=False)

        session.wait_for_exit()


@pytest.mark.parametrize('exit_code', [0, 3])
def test_success_exitcodes(pyfile, run_as, start_method, exit_code):
    @pyfile
    def code_to_debug():
        from dbgimporter import import_and_enable_debugger
        import_and_enable_debugger()
        import sys
        exit_code = eval(sys.argv[1])
        print('sys.exit(%r)' % (exit_code,))
        sys.exit(exit_code)

    with DebugSession() as session:
        session.program_args = [repr(exit_code)]
        session.success_exitcodes = [3]
        session.initialize(
            target=(run_as, code_to_debug),
            start_method=start_method,
            expected_returncode=exit_code,
        )
        session.send_request('setExceptionBreakpoints', {
            'filters': ['uncaught']
        }).wait_for_response()
        session.start_debugging()

        if exit_code == 0:
            session.wait_for_thread_stopped(reason='exception')
            session.send_request('continue').wait_for_response(freeze=False)

        session.wait_for_exit()


@pytest.mark.parametrize('max_frames', ['default', 'all', 10])
def test_exception_stack(pyfile, run_as, start_method, max_frames):
    @pyfile
    def code_to_debug():
        from dbgimporter import import_and_enable_debugger
        import_and_enable_debugger()
        def do_something(n):
            if n <= 0:
                raise ArithmeticError('bad code') # @unhandled
            do_something2(n - 1)

        def do_something2(n):
            do_something(n-1)

        do_something(100)

    if max_frames == 'all':
        # trace back compresses repeated text
        min_expected_lines = 100
        max_expected_lines = 220
        args = {'maxExceptionStackFrames': 0}
    elif max_frames == 'default':
        # default is all frames
        min_expected_lines = 100
        max_expected_lines = 220
        args = {}
    else:
        min_expected_lines = 10
        max_expected_lines = 21
        args = {'maxExceptionStackFrames': 10}

    line_numbers = get_marked_line_numbers(code_to_debug)
    with DebugSession() as session:
        session.initialize(
            target=(run_as, code_to_debug),
            start_method=start_method,
            expected_returncode=ANY.int,
            args=args,
        )
        session.send_request('setExceptionBreakpoints', {
            'filters': ['uncaught']
        }).wait_for_response()
        session.start_debugging()

        hit = session.wait_for_thread_stopped(reason='exception')
        frames = hit.stacktrace.body['stackFrames']
        assert frames[0]['line'] == line_numbers['unhandled']

        resp_exc_info = session.send_request('exceptionInfo', {
            'threadId': hit.thread_id
        }).wait_for_response()

        expected = ANY.dict_with({
            'exceptionId': Regex('ArithmeticError'),
            'description': 'bad code',
            'breakMode': 'unhandled',
            'details': ANY.dict_with({
                'typeName': Regex('ArithmeticError'),
                'message': 'bad code',
                'source': Path(code_to_debug),
            }),
        })
        assert resp_exc_info.body == expected
        stack_str = resp_exc_info.body['details']['stackTrace']
        stack_line_count = len(stack_str.split('\n'))
        assert min_expected_lines <= stack_line_count <= max_expected_lines

        session.send_request('continue').wait_for_response(freeze=False)

        session.wait_for_exit()
