# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

import platform
import pytest

from ..helpers.pattern import ANY, Pattern
from ..helpers.session import DebugSession
from ..helpers.timeline import Event


@pytest.mark.timeout(20)
@pytest.mark.skipif(platform.system() != 'Windows',
                    reason='Debugging multiprocessing module only works on Windows')
def test_multiprocessing(debug_session, pyfile):
    @pyfile
    def code_to_debug():
        import multiprocessing

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
            multiprocessing.set_start_method('spawn')
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

    debug_session.setup_backchannel()
    debug_session.multiprocess = True
    debug_session.prepare_to_run(filename=code_to_debug)
    debug_session.start_debugging()

    child_pid = debug_session.backchannel.read_json()

    child_subprocess = debug_session.wait_until(Event('ptvsd_subprocess'))
    assert child_subprocess.body in Pattern({
        'processId': child_pid,
        'port': ANY.int,
    })
    child_port = child_subprocess.body['port']

    child_session = DebugSession(method='attach_socket', ptvsd_port=child_port)
    child_session.connect()
    child_session.handshake()
    child_session.start_debugging()

    child_child_subprocess = child_session.wait_until(Event('ptvsd_subprocess'))
    assert child_child_subprocess.body in Pattern({
        'processId': ANY.int,
        'port': ANY.int,
    })
    child_child_port = child_child_subprocess.body['port']

    child_child_session = DebugSession(method='attach_socket', ptvsd_port=child_child_port)
    child_child_session.connect()
    child_child_session.handshake()
    child_child_session.start_debugging()
    child_child_session.wait_until(Event('process'))

    debug_session.backchannel.write_json('continue')

    child_child_session.send_request('disconnect')
    child_child_session.wait_for_disconnect()

    child_session.send_request('disconnect')
    child_session.wait_for_disconnect()

    debug_session.wait_for_exit()
