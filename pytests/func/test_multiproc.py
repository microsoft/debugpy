# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

import platform
import pytest
import sys

from pytests.helpers.pattern import ANY
from pytests.helpers.session import DebugSession
from pytests.helpers.timeline import Event, Request


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
            import backchannel
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

    root_start_request, = debug_session.all_occurrences_of(Request('launch') | Request('attach'))
    root_process, = debug_session.all_occurrences_of(Event('process'))
    root_pid = int(root_process.body['systemProcessId'])

    child_pid = debug_session.read_json()

    child_subprocess = debug_session.wait_for_next(Event('ptvsd_subprocess'))
    assert child_subprocess == Event('ptvsd_subprocess', {
        'rootProcessId': root_pid,
        'parentProcessId': root_pid,
        'processId': child_pid,
        'port': ANY.int,
        'rootStartRequest': {
            'seq': ANY.int,
            'type': 'request',
            'command': root_start_request.command,
            'arguments': root_start_request.arguments,
        }
    })
    child_port = child_subprocess.body['port']

    child_session = DebugSession(method='attach_socket', ptvsd_port=child_port)
    child_session.ignore_unobserved = debug_session.ignore_unobserved
    child_session.connect()
    child_session.handshake()
    child_session.start_debugging()

    debug_session.proceed()
    child_child_subprocess = debug_session.wait_for_next(Event('ptvsd_subprocess'))
    assert child_child_subprocess == Event('ptvsd_subprocess', {
        'rootProcessId': root_pid,
        'parentProcessId': child_pid,
        'processId': ANY.int,
        'port': ANY.int,
        'rootStartRequest': {
            'seq': ANY.int,
            'type': 'request',
            'command': root_start_request.command,
            'arguments': root_start_request.arguments,
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

@pytest.mark.timeout(60)
@pytest.mark.skipif(sys.version_info < (3, 0) and (platform.system() != 'Windows'),
                    reason='Bug #935')
def test_subprocess(debug_session, pyfile):
    @pyfile
    def child():
        import sys
        import backchannel
        backchannel.write_json(sys.argv)

    @pyfile
    def parent():
        import os
        import subprocess
        import sys
        argv = [sys.executable]
        argv += [sys.argv[1], '--arg1', '--arg2', '--arg3']
        env = os.environ.copy()
        process = subprocess.Popen(argv, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        process.wait()

    debug_session.multiprocess = True
    debug_session.program_args += [child]
    debug_session.prepare_to_run(filename=parent, backchannel=True)
    debug_session.start_debugging()

    root_start_request, = debug_session.all_occurrences_of(Request('launch') | Request('attach'))
    root_process, = debug_session.all_occurrences_of(Event('process'))
    root_pid = int(root_process.body['systemProcessId'])

    child_subprocess = debug_session.wait_for_next(Event('ptvsd_subprocess'))
    assert child_subprocess == Event('ptvsd_subprocess', {
        'rootProcessId': root_pid,
        'parentProcessId': root_pid,
        'processId': ANY.int,
        'port': ANY.int,
        'rootStartRequest': {
            'seq': ANY.int,
            'type': 'request',
            'command': root_start_request.command,
            'arguments': root_start_request.arguments,
        }
    })
    child_port = child_subprocess.body['port']
    debug_session.proceed()

    child_session = DebugSession(method='attach_socket', ptvsd_port=child_port)
    child_session.ignore_unobserved = debug_session.ignore_unobserved
    child_session.connect()
    child_session.handshake()
    child_session.start_debugging()

    child_argv = debug_session.read_json()
    assert child_argv == [child, '--arg1', '--arg2', '--arg3']

    debug_session.wait_for_exit()
