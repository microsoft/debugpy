# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

import platform
import pytest
import sys

from ..helpers.pattern import ANY
from ..helpers.session import DebugSession
from ..helpers.timeline import Event, Request


@pytest.mark.timeout(60)
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

            print('spawning child of child')
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

            print('spawning child')
            q = multiprocessing.Queue()
            p = multiprocessing.Process(target=child, args=(q,))
            p.start()
            print('child spawned')
            backchannel.write_json(p.pid)

            q.put(1)
            assert backchannel.read_json() == 'continue'
            q.put(2)
            p.join()
            assert q.get() == 4
            q.close()
            backchannel.write_json('done')

    debug_session.ignore_unobserved += [
        # The queue module can spawn helper background threads, depending on Python version
        # and platform. Since this is an implementation detail, we don't care about those.
        Event('thread', ANY.dict_with({'reason': 'started'}))
    ]

    debug_session.multiprocess = True
    debug_session.prepare_to_run(filename=code_to_debug, backchannel=True)
    debug_session.start_debugging()

    initial_request, = debug_session.all_occurrences_of(Request('launch') | Request('attach'))
    initial_process, = debug_session.all_occurrences_of(Event('process'))
    initial_pid = int(initial_process.body['systemProcessId'])

    child_pid = debug_session.read_json()

    child_subprocess = debug_session.wait_for_next(Event('ptvsd_subprocess'))
    assert child_subprocess == Event('ptvsd_subprocess', {
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
    child_session.ignore_unobserved = debug_session.ignore_unobserved
    child_session.connect()
    child_session.handshake()
    child_session.start_debugging()

    child_child_subprocess = child_session.wait_for_next(Event('ptvsd_subprocess'))
    assert child_child_subprocess == Event('ptvsd_subprocess', {
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
    child_child_session.ignore_unobserved = debug_session.ignore_unobserved
    child_child_session.connect()
    child_child_session.handshake()
    child_child_session.start_debugging(freeze=False)

    debug_session.write_json('continue')

    if sys.version_info >= (3,):
        child_child_session.wait_for_termination()
        child_session.wait_for_termination()
    else:
        # These should really be wait_for_termination(), but child processes don't send the
        # usual sequence of events leading to 'terminate' when they exit for some unclear
        # reason (ptvsd bug?). So, just wait till they drop connection.
        child_child_session.wait_for_disconnect()
        child_session.wait_for_disconnect()

    assert debug_session.read_json() == 'done'
