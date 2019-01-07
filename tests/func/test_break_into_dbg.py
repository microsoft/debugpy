# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

import pytest
import sys
from tests.helpers.session import DebugSession
from tests.helpers.timeline import Event


@pytest.mark.parametrize('run_as', ['file', 'module', 'code'])
def test_with_wait_for_attach(pyfile, run_as, start_method):

    @pyfile
    def code_to_debug():
        # NOTE: These tests verify break_into_debugger for launch
        # and attach cases. For attach this is always after wait_for_attach
        from dbgimporter import import_and_enable_debugger
        import_and_enable_debugger()
        import ptvsd
        ptvsd.break_into_debugger()
        print('break here')

    with DebugSession() as session:
        session.initialize(
            target=(run_as, code_to_debug),
            start_method=start_method,
            ignore_unobserved=[Event('continued')]
        )
        session.start_debugging()
        hit = session.wait_for_thread_stopped()
        frames = hit.stacktrace.body['stackFrames']
        assert frames[0]['line'] == 7

        session.send_request('continue').wait_for_response(freeze=False)
        session.wait_for_exit()


@pytest.mark.parametrize('run_as', ['file', 'module', 'code'])
@pytest.mark.skipif(sys.version_info < (3, 7), reason='Supported from 3.7+')
def test_breakpoint_function(pyfile, run_as, start_method):

    @pyfile
    def code_to_debug():
        # NOTE: These tests verify break_into_debugger for launch
        # and attach cases. For attach this is always after wait_for_attach
        from dbgimporter import import_and_enable_debugger
        import_and_enable_debugger()
        breakpoint()
        print('break here')

    with DebugSession() as session:
        session.initialize(
            target=(run_as, code_to_debug),
            start_method=start_method,
            ignore_unobserved=[Event('continued')]
        )
        session.start_debugging()
        hit = session.wait_for_thread_stopped()
        frames = hit.stacktrace.body['stackFrames']
        path = frames[0]['source']['path']
        assert path.endswith('code_to_debug.py') or path.endswith('<string>')
        assert frames[0]['line'] == 6

        session.send_request('continue').wait_for_response(freeze=False)
        session.wait_for_exit()
