# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

import os
import pytest
from tests.helpers.session import DebugSession
from tests.helpers.pathutils import get_test_root
from tests.helpers.timeline import Event
from tests.helpers.pattern import ANY
from tests.helpers import get_marked_line_numbers


@pytest.mark.parametrize('wait_for_attach', ['waitOn', 'waitOff'])
@pytest.mark.parametrize('is_attached', ['attachCheckOn', 'attachCheckOff'])
@pytest.mark.parametrize('break_into', ['break', 'pause'])
def test_attach_basic(run_as, wait_for_attach, is_attached, break_into):
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
def test_reattach(pyfile, run_as, start_method):

    @pyfile
    def code_to_debug():
        import time
        import ptvsd
        import backchannel
        from dbgimporter import import_and_enable_debugger
        import_and_enable_debugger()
        ptvsd.break_into_debugger()
        print('first')  # @break1
        backchannel.write_json('continued')
        for _ in range(0, 100):
            time.sleep(0.1)
            ptvsd.break_into_debugger()
            print('second')  # @break2

    with DebugSession() as session:
        session.initialize(
            target=(run_as, code_to_debug),
            start_method=start_method,
            use_backchannel=True,
            kill_ptvsd=False,
            skip_capture=True,
        )

        marked_line_numbers = get_marked_line_numbers(code_to_debug)

        session.start_debugging()
        hit = session.wait_for_thread_stopped()
        frames = hit.stacktrace.body['stackFrames']
        assert marked_line_numbers['break1'] == frames[0]['line']
        session.send_request('disconnect').wait_for_response(freeze=False)
        session.wait_for_disconnect()
        assert session.read_json() == 'continued'

    # re-attach
    with session.connect_with_new_session(
        target=(run_as, code_to_debug),
    ) as session2:
        session2.start_debugging()
        hit = session2.wait_for_thread_stopped()
        frames = hit.stacktrace.body['stackFrames']
        assert marked_line_numbers['break2'] == frames[0]['line']
        session2.send_request('disconnect').wait_for_response(freeze=False)
        session2.wait_for_disconnect()


def _change_wait_to_false_and_exit(session):
    # Note: don't use breakpoints. Prefer 'pause' because when 'code'
    # is used as the start_method the frame is set to <string> and not
    # the code_to_debug.py filename (and thus breakpoints don't work well).
    session.send_request('pause').wait_for_response(freeze=False)
    hit = session.wait_for_thread_stopped()
    resp_scopes = session.send_request('scopes', arguments={
        'frameId': hit.frame_id
    }).wait_for_response()
    scopes = resp_scopes.body['scopes']
    resp_variables = session.send_request('variables', arguments={
        'variablesReference': scopes[0]['variablesReference']
    }).wait_for_response()
    variables = list(v for v in resp_variables.body['variables'] if v['name'] == 'wait')
    assert len(variables) == 1
    session.send_request('setExpression', arguments={
        'frameId': hit.frame_id,
        'expression': 'wait',
        'value': 'False'
    }).wait_for_response()

    session.send_request('continue').wait_for_response(freeze=False)
    session.wait_for_exit()


@pytest.mark.parametrize('start_method', ['attach_pid'])
@pytest.mark.parametrize('run_as', ['file', 'module', 'code'])
def test_attaching_by_pid_no_threading(pyfile, run_as, start_method):

    @pyfile
    def code_to_debug():
        # import_and_enable_debugger
        import time

        wait = True
        i = 0
        while wait:
            i += 1
            print('in loop')
            time.sleep(0.1)
            if i > 100:
                raise AssertionError('Debugger did not change wait to False as expected within the timeout.')

    with DebugSession() as session:
        session.initialize(
            target=(run_as, code_to_debug),
            start_method=start_method,
        )
        session.start_debugging()
        # Wait for the first print to make sure we're in the proper state to pause.
        session.wait_for_next(Event('output', ANY.dict_with({'category': 'stdout', 'output': 'in loop'})))
        _change_wait_to_false_and_exit(session)


@pytest.mark.parametrize('start_method', ['attach_pid'])
@pytest.mark.parametrize('run_as', ['file', 'module', 'code'])
def test_attaching_by_pid_main_halted(pyfile, run_as, start_method):

    @pyfile
    def code_to_debug():
        # import_and_enable_debugger
        import time
        try:
            import _thread
        except ImportError:
            import thread as _thread

        lock = _thread.allocate_lock()
        initialized = [False]

        def new_thread_function():
            wait = True

            with lock:
                initialized[0] = True
                while wait:
                    print('in loop')
                    time.sleep(.1)  # break thread here

        _thread.start_new_thread(new_thread_function, ())

        while not initialized[0]:
            time.sleep(.1)

        with lock:  # It'll be here until the secondary thread finishes (i.e.: releases the lock).
            pass

        import threading  # Note: only import after the attach.
        curr_thread_ident = threading.current_thread().ident
        if hasattr(threading, 'main_thread'):
            main_thread_ident = threading.main_thread().ident
        else:
            # Python 2 does not have main_thread, but we can still get the reference.
            main_thread_ident = threading._shutdown.im_self.ident

        if curr_thread_ident != main_thread_ident:
            raise AssertionError('Expected current thread ident (%s) to be the main thread ident (%s)' % (
                curr_thread_ident, main_thread_ident))

    import time
    with DebugSession() as session:
        session.initialize(
            target=(run_as, code_to_debug),
            start_method=start_method,
        )
        session.start_debugging()
        session.wait_for_next(Event('output', ANY.dict_with({'category': 'stdout', 'output': 'in loop'})))
        time.sleep(1)  # Give some more time to make sure that the main thread is halted.

        _change_wait_to_false_and_exit(session)
