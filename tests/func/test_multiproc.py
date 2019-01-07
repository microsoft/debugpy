# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

import platform
import pytest
import sys

from tests.helpers.pattern import ANY
from tests.helpers.session import DebugSession
from tests.helpers.timeline import Event, Request, Response


@pytest.mark.timeout(30)
@pytest.mark.skipif(platform.system() != 'Windows',
                    reason='Debugging multiprocessing module only works on Windows')
@pytest.mark.parametrize('start_method', ['launch', 'attach_socket_cmdline'])
def test_multiprocessing(pyfile, run_as, start_method):
    @pyfile
    def code_to_debug():
        import multiprocessing
        import platform
        import sys
        from dbgimporter import import_and_enable_debugger
        import_and_enable_debugger()

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

    with DebugSession() as parent_session:
        parent_session.initialize(multiprocess=True, target=(run_as, code_to_debug), start_method=start_method, use_backchannel=True)
        parent_session.start_debugging()

        root_start_request, = parent_session.all_occurrences_of(Request('launch') | Request('attach'))
        root_process, = parent_session.all_occurrences_of(Event('process'))
        root_pid = int(root_process.body['systemProcessId'])

        child_pid = parent_session.read_json()

        child_subprocess = parent_session.wait_for_next(Event('ptvsd_subprocess'))
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
        parent_session.proceed()

        with parent_session.connect_to_child_session(child_subprocess) as child_session:
            child_session.start_debugging()

            grandchild_subprocess = parent_session.wait_for_next(Event('ptvsd_subprocess'))
            assert grandchild_subprocess == Event('ptvsd_subprocess', {
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
            parent_session.proceed()

            with parent_session.connect_to_child_session(grandchild_subprocess) as grandchild_session:
                grandchild_session.start_debugging()

                parent_session.write_json('continue')

                grandchild_session.wait_for_termination()
                child_session.wait_for_termination()

                assert parent_session.read_json() == 'done'
                parent_session.wait_for_exit()


@pytest.mark.timeout(30)
@pytest.mark.skipif(sys.version_info < (3, 0) and (platform.system() != 'Windows'),
                    reason='Bug #935')
@pytest.mark.parametrize('start_method', ['launch', 'attach_socket_cmdline'])
def test_subprocess(pyfile, run_as, start_method):
    @pyfile
    def child():
        import sys
        import backchannel
        from dbgimporter import import_and_enable_debugger
        import_and_enable_debugger()
        backchannel.write_json(sys.argv)

    @pyfile
    def parent():
        import os
        import subprocess
        import sys
        from dbgimporter import import_and_enable_debugger
        import_and_enable_debugger()
        argv = [sys.executable, sys.argv[1], '--arg1', '--arg2', '--arg3']
        env = os.environ.copy()
        process = subprocess.Popen(argv, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        process.wait()

    with DebugSession() as parent_session:
        parent_session.program_args += [child]
        parent_session.initialize(multiprocess=True, target=(run_as, parent), start_method=start_method, use_backchannel=True)
        parent_session.start_debugging()

        root_start_request, = parent_session.all_occurrences_of(Request('launch') | Request('attach'))
        root_process, = parent_session.all_occurrences_of(Event('process'))
        root_pid = int(root_process.body['systemProcessId'])

        child_subprocess = parent_session.wait_for_next(Event('ptvsd_subprocess'))
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
        parent_session.proceed()

        with parent_session.connect_to_child_session(child_subprocess) as child_session:
            child_session.start_debugging()

            child_argv = parent_session.read_json()
            assert child_argv == [child, '--arg1', '--arg2', '--arg3']

            child_session.wait_for_termination()
            parent_session.wait_for_exit()


@pytest.mark.timeout(30)
@pytest.mark.skipif(sys.version_info < (3, 0) and (platform.system() != 'Windows'),
                    reason='Bug #935')
@pytest.mark.parametrize('start_method', ['launch', 'attach_socket_cmdline'])
def test_autokill(pyfile, run_as, start_method):
    @pyfile
    def child():
        from dbgimporter import import_and_enable_debugger
        import_and_enable_debugger()
        while True:
            pass

    @pyfile
    def parent():
        import backchannel
        import os
        import subprocess
        import sys
        from dbgimporter import import_and_enable_debugger
        import_and_enable_debugger()
        argv = [sys.executable, sys.argv[1]]
        env = os.environ.copy()
        subprocess.Popen(argv, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        backchannel.read_json()

    with DebugSession() as parent_session:
        parent_session.program_args += [child]
        parent_session.initialize(multiprocess=True, target=(run_as, parent), start_method=start_method, use_backchannel=True)
        parent_session.start_debugging()

        with parent_session.connect_to_next_child_session() as child_session:
            child_session.start_debugging()

            if parent_session.start_method == 'launch':
                # In launch scenario, terminate the parent process by disconnecting from it.
                parent_session.expected_returncode = ANY
                disconnect = parent_session.send_request('disconnect', {})
                parent_session.wait_for_next(Response(disconnect))
            else:
                # In attach scenario, just let the parent process run to completion.
                parent_session.expected_returncode = 0
                parent_session.write_json(None)

            child_session.wait_for_termination()
            parent_session.wait_for_exit()
