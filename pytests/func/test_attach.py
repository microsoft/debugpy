# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

import os
import pytest
from pytests.helpers.session import DebugSession
from pytests.helpers.pathutils import get_test_root
from pytests.helpers.timeline import Event


@pytest.mark.parametrize('wait_for_attach', ['waitOn', 'waitOff'])
@pytest.mark.parametrize('is_attached', ['attachCheckOn', 'attachCheckOff'])
@pytest.mark.parametrize('break_into', ['break', 'pause'])
def test_attach(run_as, wait_for_attach, is_attached, break_into):
    testfile = os.path.join(get_test_root('attach'), 'attach1.py')

    with DebugSession() as session:
        env = {
            'PTVSD_TEST_HOST': 'localhost',
            'PTVSD_TEST_PORT': str(session.ptvsd_port),
        }
        if wait_for_attach == 'waitOn':
            env['PTVSD_WAIT_FOR_ATTACH'] = '1'
        if is_attached == 'attachCheckOn':
            env['PTVSD_IS_ATTACHED'] = '1'
        if break_into == 'break':
            env['PTVSD_BREAK_INTO_DBG'] = '1'

        session.initialize(
            target=(run_as, testfile),
            start_method='launch',
            ignore_unobserved=[Event('continued')],
            env=env,
            use_backchannel=True,
        )
        session.start_debugging()

        if wait_for_attach == 'waitOn':
            assert session.read_json() == 'wait_for_attach'

        if is_attached == 'attachCheckOn':
            assert session.read_json() == 'is_attached'

        if break_into == 'break':
            assert session.read_json() == 'break_into_debugger'
            hit = session.wait_for_thread_stopped()
            frames = hit.stacktrace.body['stackFrames']
            assert 32 == frames[0]['line']
        else:
            # pause test
            session.write_json('pause_test')
            session.send_request('pause').wait_for_response(freeze=False)
            hit = session.wait_for_thread_stopped(reason='pause')
            frames = hit.stacktrace.body['stackFrames']
            # Note: no longer asserting line as it can even stop on different files
            # (such as as backchannel.py).
            # assert frames[0]['line'] in [27, 28, 29]

        session.send_request('continue').wait_for_response(freeze=False)
        session.wait_for_exit()


@pytest.mark.parametrize('start_method', ['attach_socket_cmdline', 'attach_socket_import'])
@pytest.mark.skip(reason='Bug #1048')
def test_reattach(pyfile, run_as, start_method):
    @pyfile
    def code_to_debug():
        import time
        import ptvsd
        import backchannel
        from dbgimporter import import_and_enable_debugger
        import_and_enable_debugger()
        ptvsd.break_into_debugger()
        print('first')
        backchannel.write_json('continued')
        for _ in range(0, 20):
            time.sleep(0.1)
            ptvsd.break_into_debugger()
            print('second')

    with DebugSession() as session:
        session.initialize(
            target=(run_as, code_to_debug),
            start_method=start_method,
            ignore_unobserved=[Event('continued')],
            use_backchannel=True,
        )
        session.start_debugging()
        hit = session.wait_for_thread_stopped()
        frames = hit.stacktrace.body['stackFrames']
        assert 7 == frames[0]['line']
        session.send_request('disconnect').wait_for_response(freeze=False)
        session.wait_for_disconnect()
        assert session.read_json() == 'continued'

        # re-attach
        with session.connect_with_new_session() as session2:
            session2.start_debugging()
            hit = session2.wait_for_thread_stopped()
            frames = hit.stacktrace.body['stackFrames']
            assert 12 == frames[0]['line']
            session.send_request('continue').wait_for_response(freeze=False)
            session.wait_for_exit()
