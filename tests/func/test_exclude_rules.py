# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

from tests.helpers import print, get_marked_line_numbers
from tests.helpers.session import DebugSession
from tests.helpers.pattern import ANY, Path
from os.path import os
import pytest
from tests.helpers.pathutils import get_test_root


@pytest.mark.parametrize('scenario', [
    'exclude_by_name',
    'exclude_by_dir',
])
@pytest.mark.parametrize('exception_type', [
    'RuntimeError',
    'SysExit'
])
def test_exceptions_and_exclude_rules(pyfile, run_as, start_method, scenario, exception_type):

    if exception_type == 'RuntimeError':

        @pyfile
        def code_to_debug():
            from dbgimporter import import_and_enable_debugger
            import_and_enable_debugger()
            raise RuntimeError('unhandled error')  # @raise_line

    elif exception_type == 'SysExit':

        @pyfile
        def code_to_debug():
            from dbgimporter import import_and_enable_debugger
            import sys
            import_and_enable_debugger()
            sys.exit(1)  # @raise_line

    else:
        raise AssertionError('Unexpected exception_type: %s' % (exception_type,))

    if scenario == 'exclude_by_name':
        rules = [{'path': '**/' + os.path.basename(code_to_debug), 'include': False}]
    elif scenario == 'exclude_by_dir':
        rules = [{'path': os.path.dirname(code_to_debug), 'include': False}]
    else:
        raise AssertionError('Unexpected scenario: %s' % (scenario,))

    with DebugSession() as session:
        session.initialize(
            target=(run_as, code_to_debug),
            start_method=start_method,
            rules=rules,
        )
        # TODO: The process returncode doesn't match the one returned from the DAP.
        # See: https://github.com/Microsoft/ptvsd/issues/1278
        session.expected_returncode = ANY.int
        filters = ['raised', 'uncaught']

        session.send_request('setExceptionBreakpoints', {
            'filters': filters
        }).wait_for_response()
        session.start_debugging()

        # No exceptions should be seen.
        session.wait_for_exit()


@pytest.mark.parametrize('scenario', [
    'exclude_code_to_debug',
    'exclude_callback_dir',
])
def test_exceptions_and_partial_exclude_rules(pyfile, run_as, start_method, scenario):

    @pyfile
    def code_to_debug():
        from dbgimporter import import_and_enable_debugger
        import_and_enable_debugger()

        import backchannel
        import sys
        json = backchannel.read_json()
        call_me_back_dir = json['call_me_back_dir']
        sys.path.append(call_me_back_dir)

        import call_me_back

        def call_func():
            raise RuntimeError('unhandled error')  # @raise_line

        call_me_back.call_me_back(call_func)  # @call_me_back_line
        print('done')

    line_numbers = get_marked_line_numbers(code_to_debug)
    call_me_back_dir = get_test_root('call_me_back')

    if scenario == 'exclude_code_to_debug':
        rules = [
            {'path': '**/' + os.path.basename(code_to_debug), 'include': False}
        ]
    elif scenario == 'exclude_callback_dir':
        rules = [
            {'path': call_me_back_dir, 'include': False}
        ]
    else:
        raise AssertionError('Unexpected scenario: %s' % (scenario,))

    with DebugSession() as session:
        session.initialize(
            target=(run_as, code_to_debug),
            start_method=start_method,
            use_backchannel=True,
            rules=rules,
        )
        # TODO: The process returncode doesn't match the one returned from the DAP.
        # See: https://github.com/Microsoft/ptvsd/issues/1278
        session.expected_returncode = ANY.int
        filters = ['raised', 'uncaught']

        session.send_request('setExceptionBreakpoints', {
            'filters': filters
        }).wait_for_response()
        session.start_debugging()
        session.write_json({'call_me_back_dir': call_me_back_dir})

        if scenario == 'exclude_code_to_debug':
            # Stop at handled
            hit = session.wait_for_thread_stopped(reason='exception')
            frames = hit.stacktrace.body['stackFrames']
            # We don't stop at the raise line but rather at the callback module which is
            # not excluded.
            assert len(frames) == 2
            assert frames[0] == ANY.dict_with({
                'line': 2,
                'source': ANY.dict_with({
                    'path': Path(os.path.join(call_me_back_dir, 'call_me_back.py'))
                })
            })
            assert frames[1] == ANY.dict_with({
                'line': line_numbers['call_me_back_line'],
                'source': ANY.dict_with({
                    'path': Path(code_to_debug)
                })
            })
            # 'continue' should terminate the debuggee
            session.send_request('continue').wait_for_response(freeze=False)

            # Note: does not stop at unhandled exception because raise was in excluded file.

        elif scenario == 'exclude_callback_dir':
            # Stop at handled raise_line
            hit = session.wait_for_thread_stopped(reason='exception')
            frames = hit.stacktrace.body['stackFrames']
            assert len(frames) == 3
            assert frames[0] == ANY.dict_with({
                'line': line_numbers['raise_line'],
                'source': ANY.dict_with({
                    'path': Path(code_to_debug)
                })
            })
            session.send_request('continue').wait_for_response()

            # Stop at handled call_me_back_line
            hit = session.wait_for_thread_stopped(reason='exception')
            frames = hit.stacktrace.body['stackFrames']
            assert len(frames) == 1
            assert frames[0] == ANY.dict_with({
                'line': line_numbers['call_me_back_line'],
                'source': ANY.dict_with({
                    'path': Path(code_to_debug)
                })
            })
            session.send_request('continue').wait_for_response()

            # Stop at unhandled
            hit = session.wait_for_thread_stopped(reason='exception')
            frames = hit.stacktrace.body['stackFrames']
            assert len(frames) == 3
            assert frames[0] == ANY.dict_with({
                'line': line_numbers['raise_line'],
                'source': ANY.dict_with({
                    'path': Path(code_to_debug)
                })
            })
            session.send_request('continue').wait_for_response(freeze=False)
        else:
            raise AssertionError('Unexpected scenario: %s' % (scenario,))

        session.wait_for_exit()
