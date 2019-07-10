# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import platform
import pytest
import sys

from tests import debug
from tests.patterns import some
from tests.timeline import Event, Request


@pytest.mark.timeout(30)
@pytest.mark.skipif(
    platform.system() != "Windows",
    reason="Debugging multiprocessing module only works on Windows",
)
@pytest.mark.parametrize("start_method", ["launch", "attach_socket_cmdline"])
def test_multiprocessing(pyfile, start_method, run_as):
    @pyfile
    def code_to_debug():
        import multiprocessing
        import platform
        import sys
        import debug_me  # noqa

        def child_of_child(q):
            print("entering child of child")
            assert q.get() == 2
            q.put(3)
            print("leaving child of child")

        def child(q):
            print("entering child")
            assert q.get() == 1

            print("spawning child of child")
            p = multiprocessing.Process(target=child_of_child, args=(q,))
            p.start()
            p.join()

            assert q.get() == 3
            q.put(4)
            print("leaving child")

        if __name__ == "__main__":
            from debug_me import backchannel

            if sys.version_info >= (3, 4):
                multiprocessing.set_start_method("spawn")
            else:
                assert platform.system() == "Windows"

            print("spawning child")
            q = multiprocessing.Queue()
            p = multiprocessing.Process(target=child, args=(q,))
            p.start()
            print("child spawned")
            backchannel.send(p.pid)

            q.put(1)
            assert backchannel.receive() == "continue"
            q.put(2)
            p.join()
            assert q.get() == 4
            q.close()
            backchannel.send("done")

    with debug.Session() as parent_session:
        parent_backchannel = parent_session.setup_backchannel()
        parent_session.initialize(
            multiprocess=True,
            target=(run_as, code_to_debug),
            start_method=start_method,
        )
        parent_session.start_debugging()

        root_start_request, = parent_session.all_occurrences_of(
            Request("launch") | Request("attach")
        )
        root_process, = parent_session.all_occurrences_of(Event("process"))
        root_pid = int(root_process.body["systemProcessId"])

        child_pid = parent_backchannel.receive()

        child_subprocess = parent_session.wait_for_next(Event("ptvsd_subprocess"))
        assert child_subprocess == Event(
            "ptvsd_subprocess",
            {
                "rootProcessId": root_pid,
                "parentProcessId": root_pid,
                "processId": child_pid,
                "port": some.int,
                "rootStartRequest": {
                    "seq": some.int,
                    "type": "request",
                    "command": root_start_request.command,
                    "arguments": root_start_request.arguments,
                },
            },
        )
        parent_session.proceed()

        with parent_session.attach_to_subprocess(child_subprocess) as child_session:
            child_session.start_debugging()

            grandchild_subprocess = parent_session.wait_for_next(
                Event("ptvsd_subprocess")
            )
            assert grandchild_subprocess == Event(
                "ptvsd_subprocess",
                {
                    "rootProcessId": root_pid,
                    "parentProcessId": child_pid,
                    "processId": some.int,
                    "port": some.int,
                    "rootStartRequest": {
                        "seq": some.int,
                        "type": "request",
                        "command": root_start_request.command,
                        "arguments": root_start_request.arguments,
                    },
                },
            )
            parent_session.proceed()

            with parent_session.attach_to_subprocess(
                grandchild_subprocess
            ) as grandchild_session:
                grandchild_session.start_debugging()

                parent_backchannel.send("continue")

                grandchild_session.wait_for_termination()
                child_session.wait_for_termination()

                assert parent_backchannel.receive() == "done"
                parent_session.wait_for_exit()


@pytest.mark.timeout(30)
@pytest.mark.skipif(
    sys.version_info < (3, 0) and (platform.system() != "Windows"), reason="Bug #935"
)
@pytest.mark.parametrize("start_method", ["launch", "attach_socket_cmdline"])
def test_subprocess(pyfile, start_method, run_as):
    @pyfile
    def child():
        import sys
        from debug_me import backchannel

        backchannel.send(sys.argv)

    @pyfile
    def parent():
        import os
        import subprocess
        import sys
        import debug_me  # noqa

        argv = [sys.executable, sys.argv[1], "--arg1", "--arg2", "--arg3"]
        env = os.environ.copy()
        process = subprocess.Popen(
            argv,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        process.wait()

    with debug.Session() as parent_session:
        parent_session.program_args += [child]
        parent_backchannel = parent_session.setup_backchannel()
        parent_session.initialize(
            multiprocess=True,
            target=(run_as, parent),
            start_method=start_method,
        )
        parent_session.start_debugging()

        root_start_request, = parent_session.all_occurrences_of(
            Request("launch") | Request("attach")
        )
        root_process, = parent_session.all_occurrences_of(Event("process"))
        root_pid = int(root_process.body["systemProcessId"])

        child_subprocess = parent_session.wait_for_next(Event("ptvsd_subprocess"))
        assert child_subprocess == Event(
            "ptvsd_subprocess",
            {
                "rootProcessId": root_pid,
                "parentProcessId": root_pid,
                "processId": some.int,
                "port": some.int,
                "rootStartRequest": {
                    "seq": some.int,
                    "type": "request",
                    "command": root_start_request.command,
                    "arguments": root_start_request.arguments,
                },
            },
        )
        parent_session.proceed()

        with parent_session.attach_to_subprocess(child_subprocess) as child_session:
            child_session.start_debugging()

            child_argv = parent_backchannel.receive()
            assert child_argv == [child, "--arg1", "--arg2", "--arg3"]

            child_session.wait_for_termination()
            parent_session.wait_for_exit()


@pytest.mark.timeout(30)
@pytest.mark.skipif(
    sys.version_info < (3, 0) and (platform.system() != "Windows"), reason="Bug #935"
)
@pytest.mark.parametrize("start_method", ["launch", "attach_socket_cmdline"])
def test_autokill(pyfile, start_method, run_as):
    @pyfile
    def child():
        import debug_me  # noqa

        while True:
            pass

    @pyfile
    def parent():
        import os
        import subprocess
        import sys
        from debug_me import backchannel

        argv = [sys.executable, sys.argv[1]]
        env = os.environ.copy()
        subprocess.Popen(
            argv,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        backchannel.receive()

    with debug.Session() as parent_session:
        parent_session.program_args += [child]
        parent_backchannel = parent_session.setup_backchannel()
        parent_session.initialize(
            multiprocess=True,
            target=(run_as, parent),
            start_method=start_method,
        )
        parent_session.start_debugging()

        with parent_session.attach_to_next_subprocess() as child_session:
            child_session.start_debugging()

            if parent_session.start_method == "launch":
                # In launch scenario, terminate the parent process by disconnecting from it.
                parent_session.expected_returncode = some.int
                try:
                    parent_session.request("disconnect")
                except EOFError:
                    pass
                parent_session.wait_for_disconnect()
            else:
                # In attach scenario, just let the parent process run to completion.
                parent_session.expected_returncode = 0
                parent_backchannel.send(None)

            child_session.wait_for_termination()
            parent_session.wait_for_exit()


@pytest.mark.skipif(
    sys.version_info < (3, 0) and (platform.system() != "Windows"), reason="Bug #935"
)
def test_argv_quoting(pyfile, start_method, run_as):
    @pyfile
    def args():
        import debug_me  # noqa

        args = [  # noqa
            r"regular",
            r"",
            r"with spaces" r'"quoted"',
            r'" quote at start',
            r'quote at end "',
            r'quote in " the middle',
            r'quotes "in the" middle',
            r"\path with\spaces",
            r"\path\with\terminal\backslash" + "\\",
            r"backslash \" before quote",
        ]

    @pyfile
    def parent():
        import debug_me  # noqa

        import sys
        import subprocess
        from args import args

        child = sys.argv[1]
        subprocess.check_call([sys.executable] + [child] + args)

    @pyfile
    def child():
        from debug_me import backchannel
        import sys

        from args import args as expected_args

        backchannel.send(expected_args)

        actual_args = sys.argv[1:]
        backchannel.send(actual_args)

    with debug.Session() as session:
        backchannel = session.setup_backchannel()
        session.initialize(
            target=(run_as, parent),
            start_method=start_method,
            program_args=[child],
        )

        session.start_debugging()

        expected_args = backchannel.receive()
        actual_args = backchannel.receive()
        assert expected_args == actual_args

        session.wait_for_exit()
