# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

import platform
import pytest

from ..helpers.pattern import ANY, Pattern
from ..helpers.session import DebugSession
from ..helpers.timeline import Event, Request


@pytest.mark.timeout(40)
@pytest.mark.skipif(platform.system() != 'Windows',
                    reason='Debugging multiprocessing module only works on Windows')
def test_multiprocessing(debug_session, pyfile):
    @pyfile
    def code_to_debug():
        import multiprocessing
        import platform
        import sys

        def child_of_child(q):
            print('entering child of child')
            assert q.get() == 2
            q.put(3)
            print('leaving child of child')

        def child(q):
            print('entering child')
            assert q.get() == 1
            p = multiprocessing.Process(target=child_of_child, args=(q,))
            p.start()
            p.join()
            assert q.get() == 3
            q.put(4)
            print('leaving child')

        if __name__ == '__main__':
            import pytests.helpers.backchannel as backchannel
            if sys.version_info >= (3, 4):
                multiprocessing.set_start_method('spawn')
            else:
                assert platform.system() == 'Windows'

            q = multiprocessing.Queue()
            p = multiprocessing.Process(target=child, args=(q,))
            p.start()
            backchannel.write_json(p.pid)
            q.put(1)
            assert backchannel.read_json() == 'continue'
            q.put(2)
            p.join()
            assert q.get() == 4
            q.close()

    debug_session.multiprocess = True
    debug_session.prepare_to_run(filename=code_to_debug, backchannel=True)
    start = debug_session.start_debugging()

    with debug_session.timeline.frozen():
        initial_request, = debug_session.timeline.all_occurrences_of(Request('launch') | Request('attach'))
    initial_process = (start >> Event('process')).wait()
    initial_pid = int(initial_process.body['systemProcessId'])

    child_pid = debug_session.backchannel.read_json()

    child_subprocess = (start >> Event('ptvsd_subprocess')).wait()
    assert child_subprocess.body == Pattern({
        'initialProcessId': initial_pid,
        'parentProcessId': initial_pid,
        'processId': child_pid,
        'port': ANY.int,
        'initialRequest': {
            'command': initial_request.command,
            'arguments': initial_request.arguments,
        }
    })
    child_port = child_subprocess.body['port']

    child_session = DebugSession(method='attach_socket', ptvsd_port=child_port)
    child_session.connect()
    child_session.handshake()
    child_start = child_session.start_debugging()

    child_child_subprocess = (child_start >> Event('ptvsd_subprocess')).wait()
    assert child_child_subprocess.body == Pattern({
        'initialProcessId': initial_pid,
        'parentProcessId': child_pid,
        'processId': ANY.int,
        'port': ANY.int,
        'initialRequest': {
            'command': initial_request.command,
            'arguments': initial_request.arguments,
        }
    })
    child_child_port = child_child_subprocess.body['port']

    child_child_session = DebugSession(method='attach_socket', ptvsd_port=child_child_port)
    child_child_session.connect()
    child_child_session.handshake()
    child_child_start = child_child_session.start_debugging()
    (child_child_start >> Event('process')).wait()

    debug_session.backchannel.write_json('continue')

    child_child_session.send_request('disconnect')
    child_child_session.wait_for_disconnect()

    child_session.send_request('disconnect')
    child_session.wait_for_disconnect()

    debug_session.wait_for_exit()
