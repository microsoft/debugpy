# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

import os.path
import pytest
from pytests.helpers.pattern import ANY
from pytests.helpers.session import DebugSession
from pytests.helpers.timeline import Event


@pytest.mark.parametrize('start_method', ['attach_socket_cmdline', 'attach_socket_import'])
def test_continue_on_disconnect_for_attach(pyfile, run_as, start_method):
    @pyfile
    def code_to_debug():
        from dbgimporter import import_and_enable_debugger
        import_and_enable_debugger()
        import backchannel
        backchannel.write_json('continued')
    bp_line = 4
    with DebugSession() as session:
        session.initialize(
                target=(run_as, code_to_debug),
                start_method=start_method,
                ignore_unobserved=[Event('continued'), Event('exited'), Event('terminated')],
                use_backchannel=True,
            )
        session.set_breakpoints(code_to_debug, [bp_line])
        session.start_debugging()
        hit = session.wait_for_thread_stopped('breakpoint')
        frames = hit.stacktrace.body['stackFrames']
        assert frames[0]['line'] == bp_line
        session.send_request('disconnect').wait_for_response()
        session.wait_for_disconnect()
        assert 'continued' == session.read_json()


@pytest.mark.parametrize('start_method', ['launch'])
@pytest.mark.skip(reason='Bug #1052')
def test_exit_on_disconnect_for_launch(pyfile, run_as, start_method):
    @pyfile
    def code_to_debug():
        from dbgimporter import import_and_enable_debugger
        import_and_enable_debugger()
        import os.path
        fp = os.join(os.path.dirname(os.path.abspath(__file__)), 'here.txt')
        # should not execute this
        with open(fp, 'w') as f:
            print('Should not continue after disconnect on launch', file=f)
    bp_line = 4
    with DebugSession() as session:
        session.initialize(
                target=(run_as, code_to_debug),
                start_method=start_method,
                ignore_unobserved=[Event('continued')],
                use_backchannel=True,
                expected_returncode=ANY.int,
            )
        session.set_breakpoints(code_to_debug, [bp_line])
        session.start_debugging()
        hit = session.wait_for_thread_stopped('breakpoint')
        frames = hit.stacktrace.body['stackFrames']
        assert frames[0]['line'] == bp_line
        session.send_request('disconnect').wait_for_response()
        session.wait_for_exit()
        fp = os.join(os.path.dirname(os.path.abspath(code_to_debug)), 'here.txt')
        assert not os.path.exists(fp)
