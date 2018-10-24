# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

import platform
import pytest
import sys

from pytests.helpers import print
from pytests.helpers.pattern import ANY
from pytests.helpers.timeline import Event


def _common_setup(debug_session, path, run_as):
    debug_session.ignore_unobserved += [
        Event('thread', ANY.dict_with({'reason': 'started'})),
        Event('module')
    ]
    if run_as == 'file':
        debug_session.prepare_to_run(filename=path)
    elif run_as == 'module':
        debug_session.add_file_to_pythonpath(path)
        debug_session.prepare_to_run(module='code_to_debug')
    elif run_as == 'code':
        with open(path, 'r') as f:
            code = f.read()
        debug_session.prepare_to_run(code=code)
    else:
        pytest.fail()


@pytest.mark.parametrize('run_as', ['file', 'module'])
def test_break_on_entry(debug_session, pyfile, run_as):
    @pyfile
    def code_to_debug():
        print('one')
        print('two')
        print('three')

    debug_session.debug_options += ['StopOnEntry']
    _common_setup(debug_session, code_to_debug, run_as)
    debug_session.start_debugging()

    if debug_session.method == 'launch':
        thread_stopped = debug_session.wait_for_next(Event('stopped'), ANY.dict_with({'reason': 'step'}))
        assert thread_stopped.body['threadId'] is not None

        tid = thread_stopped.body['threadId']

        resp_stacktrace = debug_session.send_request('stackTrace', arguments={
            'threadId': tid,
        }).wait_for_response()
        assert resp_stacktrace.body['totalFrames'] > 0
        frames = resp_stacktrace.body['stackFrames']
        assert frames[0]['line'] == 1

        debug_session.send_request('continue').wait_for_response()
        debug_session.wait_for_next(Event('continued'))

    debug_session.wait_for_next(Event('exited'))
    output = [e.body['output'] for e in debug_session.all_occurrences_of(Event('output'))
              if len(e.body['output']) >= 3 and e.body['category'] == 'stdout']
    assert len(output) == 3
    assert output == ['one', 'two', 'three']

    debug_session.wait_for_exit()


@pytest.mark.parametrize('run_as', ['file', 'module'])
@pytest.mark.skipif(sys.version_info < (3, 0) and platform.system() == 'Windows',
                    reason="On windows py2.7 unable to send key strokes to test.")
def test_wait_on_normal_exit_enabled(debug_session, pyfile, run_as):
    @pyfile
    def code_to_debug():
        print('one')
        print('two')
        print('three')

    debug_session.debug_options += ['WaitOnNormalExit']

    bp_line = 3
    bp_file = code_to_debug
    _common_setup(debug_session, bp_file, run_as)

    debug_session.send_request('setBreakpoints', arguments={
        'source': {'path': bp_file},
        'breakpoints': [{'line': bp_line}, ],
    }).wait_for_response()
    debug_session.start_debugging()

    debug_session.wait_for_next(Event('stopped'), ANY.dict_with({'reason': 'breakpoint'}))
    debug_session.send_request('continue').wait_for_response()
    debug_session.wait_for_next(Event('continued'))
    debug_session.proceed()

    debug_session.expected_returncode = ANY.int

    debug_session.wait_for_next(Event('exited'))
    output = [e.body['output'] for e in debug_session.all_occurrences_of(Event('output'))
              if len(e.body['output']) >= 3 and e.body['category'] == 'stdout']
    assert len(output) == 3
    assert output == ['one', 'two', 'three']

    debug_session.process.stdin.write(b' \r\n')
    debug_session.wait_for_exit()

    def _decode(text):
        if isinstance(text, bytes):
            return text.decode('utf-8')
        return text
    assert any(l for l in debug_session.output_data['OUT']
               if _decode(l).startswith('Press'))


@pytest.mark.parametrize('run_as', ['file', 'module'])
@pytest.mark.skipif(sys.version_info < (3, 0) and platform.system() == 'Windows',
                    reason="On windows py2.7 unable to send key strokes to test.")
def test_wait_on_abnormal_exit_enabled(debug_session, pyfile, run_as):
    @pyfile
    def code_to_debug():
        import sys
        print('one')
        print('two')
        print('three')
        sys.exit(12345)

    debug_session.debug_options += ['WaitOnAbnormalExit']

    bp_line = 5
    bp_file = code_to_debug
    _common_setup(debug_session, bp_file, run_as)

    debug_session.send_request('setBreakpoints', arguments={
        'source': {'path': bp_file},
        'breakpoints': [{'line': bp_line}, ],
    }).wait_for_response()
    debug_session.start_debugging()

    debug_session.wait_for_next(Event('stopped'), ANY.dict_with({'reason': 'breakpoint'}))
    debug_session.send_request('continue').wait_for_response()
    debug_session.wait_for_next(Event('continued'))
    debug_session.proceed()

    debug_session.expected_returncode = ANY.int

    debug_session.wait_for_next(Event('exited'))
    output = [e.body['output'] for e in debug_session.all_occurrences_of(Event('output'))
              if len(e.body['output']) >= 3 and e.body['category'] == 'stdout']
    assert len(output) == 3
    assert output == ['one', 'two', 'three']

    debug_session.process.stdin.write(b' \r\n')
    debug_session.wait_for_exit()

    def _decode(text):
        if isinstance(text, bytes):
            return text.decode('utf-8')
        return text
    assert any(l for l in debug_session.output_data['OUT']
               if _decode(l).startswith('Press'))


@pytest.mark.parametrize('run_as', ['file', 'module'])
def test_exit_normally_with_wait_on_abnormal_exit_enabled(debug_session, pyfile, run_as):
    @pyfile
    def code_to_debug():
        print('one')
        print('two')
        print('three')

    debug_session.debug_options += ['WaitOnAbnormalExit']

    bp_line = 3
    bp_file = code_to_debug
    _common_setup(debug_session, bp_file, run_as)

    debug_session.send_request('setBreakpoints', arguments={
        'source': {'path': bp_file},
        'breakpoints': [{'line': bp_line}, ],
    }).wait_for_response()
    debug_session.start_debugging()

    debug_session.wait_for_next(Event('stopped'), ANY.dict_with({'reason': 'breakpoint'}))
    debug_session.send_request('continue').wait_for_response()
    debug_session.wait_for_next(Event('continued'))
    debug_session.proceed()

    debug_session.wait_for_next(Event('exited'))
    output = [e.body['output'] for e in debug_session.all_occurrences_of(Event('output'))
              if len(e.body['output']) >= 3 and e.body['category'] == 'stdout']
    assert len(output) == 3
    assert output == ['one', 'two', 'three']

    debug_session.wait_for_exit()
