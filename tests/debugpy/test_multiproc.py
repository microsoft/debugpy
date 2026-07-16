# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import os
import psutil
import pytest
import sys

import debugpy
import tests
from tests import debug, log, timeline
from tests.debug import runners
from tests.patterns import some


if not tests.full:

    @pytest.fixture(params=[runners.launch] + runners.all_attach_socket)
    def run(request):
        return request.param


def expected_subprocess_config(parent_session):
    config = dict(parent_session.config)
    for key in "args", "listen", "postDebugTask", "preLaunchTask", "processId":
        config.pop(key, None)
    for key in "python", "pythonArgs", "pythonPath":
        if key in config:
            config[key] = some.thing
    config.update(
        {
            "name": some.str,
            "request": "attach",
            "subProcessId": some.int,
            "connect": {"host": some.str, "port": some.int},
        }
    )
    return config


@pytest.mark.parametrize(
    "start_method",
    ["spawn"] if sys.platform == "win32" else ["spawn", "fork"],
)
def test_multiprocessing(pyfile, target, run, start_method):
    if start_method == "spawn" and sys.platform != "win32":
        pytest.skip("https://github.com/microsoft/ptvsd/issues/1887")

    @pyfile
    def code_to_debug():
        import debuggee
        import multiprocessing
        import os
        import sys

        # https://github.com/microsoft/ptvsd/issues/2108
        class Foo(object):
            pass

        def parent(q, a):
            from debuggee import backchannel

            debuggee.setup()

            print("spawning child")
            p = multiprocessing.Process(target=child, args=(q, a))
            p.start()
            print("child spawned")

            q.put("foo?")
            foo = a.get()
            assert isinstance(foo, Foo), repr(foo)

            q.put("child_pid?")
            what, child_pid = a.get()
            assert what == "child_pid"
            backchannel.send(child_pid)

            q.put("grandchild_pid?")
            what, grandchild_pid = a.get()
            assert what == "grandchild_pid"
            backchannel.send(grandchild_pid)

            assert backchannel.receive() == "continue"
            q.put("exit!")
            p.join()

        def child(q, a):
            print("entering child")  # @bp
            assert q.get() == "foo?"
            a.put(Foo())

            assert q.get() == "child_pid?"
            a.put(("child_pid", os.getpid()))

            print("spawning child of child")
            p = multiprocessing.Process(target=grandchild, args=(q, a))
            p.start()
            p.join()

            print("leaving child")

        def grandchild(q, a):
            print("entering grandchild")
            assert q.get() == "grandchild_pid?"
            a.put(("grandchild_pid", os.getpid()))

            assert q.get() == "exit!"
            print("leaving grandchild")

        if __name__ == "__main__":
            start_method = sys.argv[1]
            if start_method != "":
                multiprocessing.set_start_method(start_method)

            q = multiprocessing.Queue()
            a = multiprocessing.Queue()
            try:
                parent(q, a)
            finally:
                q.close()
                a.close()

    with debug.Session() as parent_session:
        parent_backchannel = parent_session.open_backchannel()

        with run(parent_session, target(code_to_debug, args=[start_method])):
            pass

        expected_child_config = expected_subprocess_config(parent_session)
        child_config = parent_session.wait_for_next_event("debugpyAttach")
        child_config.pop("isOutputRedirected", None)
        assert child_config == expected_child_config
        parent_session.proceed()

        with debug.Session(child_config) as child_session:
            with child_session.start():
                child_session.set_breakpoints(code_to_debug, all)

            expected_frame = some.dap.frame(code_to_debug, line="bp")
            stop = child_session.wait_for_stop(
                "breakpoint",
                expected_frames=[expected_frame],
            )
            child_session.request('stepIn', {"threadId": stop.thread_id})

            stop = child_session.wait_for_stop(
                "step",
                expected_frames=[some.dap.frame(code_to_debug, line=expected_frame.items['line'] + 1)],
            )
            child_session.request_continue()

            expected_grandchild_config = expected_subprocess_config(child_session)
            grandchild_config = child_session.wait_for_next_event("debugpyAttach")
            grandchild_config.pop("isOutputRedirected", None)
            assert grandchild_config == expected_grandchild_config

            with debug.Session(grandchild_config) as grandchild_session:
                with grandchild_session.start():
                    pass

                parent_backchannel.send("continue")


@pytest.mark.parametrize("subProcess", [True, False, None])
@pytest.mark.parametrize("method", ["startDebugging", "debugpyAttach", ""])
def test_subprocess(pyfile, target, run, subProcess, method):
    @pyfile
    def child():
        import os
        import sys

        assert "debugpy" in sys.modules

        import debugpy
        from debuggee import backchannel

        backchannel.send(os.getpid())
        backchannel.send(debugpy.__file__)
        backchannel.send(sys.argv)

    @pyfile
    def parent():
        import debuggee
        import os
        import subprocess
        import sys

        debuggee.setup()
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
        backchannel = parent_session.open_backchannel()

        if method:
            parent_session.capabilities["supportsStartDebuggingRequest"] = (method == "startDebugging")
        parent_session.config["preLaunchTask"] = "doSomething"
        parent_session.config["postDebugTask"] = "doSomethingElse"
        if subProcess is not None:
            parent_session.config["subProcess"] = subProcess

        with run(parent_session, target(parent, args=[child])):
            pass

        if subProcess is False:
            return

        expected_child_config = expected_subprocess_config(parent_session)

        if method == "startDebugging":
            subprocess_request = parent_session.timeline.wait_for_next(timeline.Request("startDebugging"))
            child_config = subprocess_request.arguments("configuration", dict)
            del expected_child_config["request"]
        else:
            child_config = parent_session.wait_for_next_event("debugpyAttach")

        child_config = dict(child_config)
        child_config.pop("isOutputRedirected", None)
        assert child_config == expected_child_config
        child_config["request"] = "attach"

        parent_session.proceed()

        with debug.Session(child_config) as child_session:
            with child_session.start():
                pass

            child_pid = backchannel.receive()
            assert child_pid == child_config["subProcessId"]
            assert str(child_pid) in child_config["name"]

            debugpy_file = backchannel.receive()
            assert os.path.abspath(debugpy_file) == os.path.abspath(debugpy.__file__)

            child_argv = backchannel.receive()
            assert child_argv == [child, "--arg1", "--arg2", "--arg3"]


@pytest.mark.parametrize("run", runners.all_launch)
def test_autokill(pyfile, target, run):
    @pyfile
    def child():
        import os
        from debuggee import backchannel

        backchannel.send(os.getpid())
        while True:
            pass

    @pyfile
    def parent():
        import debuggee
        import os
        import subprocess
        import sys

        debuggee.setup()
        argv = [sys.executable, sys.argv[1]]
        env = os.environ.copy()
        subprocess.Popen(
            argv,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ).wait()

    with debug.Session() as parent_session:
        parent_session.expected_exit_code = some.int

        backchannel = parent_session.open_backchannel()
        with run(parent_session, target(parent, args=[child])):
            pass

        child_config = parent_session.wait_for_next_event("debugpyAttach")
        parent_session.proceed()

        with debug.Session(child_config) as child_session:
            with child_session.start():
                pass

            child_pid = backchannel.receive()
            assert child_config["subProcessId"] == child_pid
            child_process = psutil.Process(child_pid)

            parent_session.request("terminate")
            child_session.wait_for_exit()

    log.info("Waiting for child process...")
    child_process.wait()


@pytest.mark.parametrize("run", runners.all_launch)
def test_autokill_nodebug(pyfile, target, run):
    @pyfile
    def child():
        import os
        from debuggee import backchannel

        backchannel.send(os.getpid())
        while True:
            pass

    @pyfile
    def parent():
        import os
        import subprocess
        import sys

        argv = [sys.executable, sys.argv[1]]
        env = os.environ.copy()
        subprocess.Popen(
            argv,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ).wait()

    with debug.Session() as session:
        session.expected_exit_code = some.int
        session.config["noDebug"] = True

        backchannel = session.open_backchannel()
        run(session, target(parent, args=[child]))

        child_pid = backchannel.receive()
        child_process = psutil.Process(child_pid)

        session.request("terminate")

    log.info("Waiting for child process...")
    child_process.wait()


def test_argv_quoting(pyfile, target, run):
    @pyfile
    def args():
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
        import debuggee
        import sys
        import subprocess
        from args import args

        debuggee.setup()
        child = sys.argv[1]
        subprocess.check_call([sys.executable] + [child] + args)

    @pyfile
    def child():
        import sys
        from debuggee import backchannel
        from args import args as expected_args

        backchannel.send(expected_args)

        actual_args = sys.argv[1:]
        backchannel.send(actual_args)

    with debug.Session() as parent_session:
        backchannel = parent_session.open_backchannel()

        with run(parent_session, target(parent, args=[child])):
            pass

        child_config = parent_session.wait_for_next_event("debugpyAttach")
        parent_session.proceed()

        with debug.Session(child_config) as child_session:
            with child_session.start():
                pass

            expected_args = backchannel.receive()
            actual_args = backchannel.receive()

            assert expected_args == actual_args


def test_echo_and_shell(pyfile, target, run):
    """
    Checks https://github.com/microsoft/ptvsd/issues/1548
    """

    @pyfile
    def code_to_run():
        import debuggee
        import sys
        import subprocess
        import os

        debuggee.setup()

        if sys.platform == "win32":
            args = ["dir", "-c", "."]
        else:
            args = ["ls", "-c", "-la"]

        p = subprocess.Popen(
            args,
            shell=True,
            stderr=subprocess.STDOUT,
            stdout=subprocess.PIPE,
            cwd=os.path.dirname(os.path.abspath(__file__)),
        )
        stdout, _stderr = p.communicate()
        stdout = stdout.decode("utf-8")

        if "code_to_run.py" not in stdout:
            raise AssertionError(
                'Did not find "code_to_run.py" when listing this dir with subprocess. Contents: %s'
                % (stdout,)
            )

    with debug.Session() as parent_session:
        with run(parent_session, target(code_to_run)):
            pass


@pytest.mark.parametrize("run", runners.all_attach_connect)
@pytest.mark.parametrize("wait", ["wait", ""])
def test_subprocess_unobserved(pyfile, run, target, wait):
    @pyfile
    def child():
        from debuggee import backchannel  # @bp

        backchannel.send("child running")
        backchannel.receive()

    @pyfile
    def parent():
        import debuggee
        import os
        import subprocess
        import sys

        debuggee.setup()
        args = [sys.executable, sys.argv[1]]
        env = os.environ.copy()
        subprocess.Popen(args, env=env).wait()

    with debug.Session() as parent_session:
        backchannel = parent_session.open_backchannel()

        if not wait:
            # The child process should have started running user code as soon as it's
            # spawned, before there is a client connection.
            def before_connect(address):
                assert backchannel.receive() == "child running"

            parent_session.before_connect = before_connect

        with run(parent_session, target(parent, args=[child]), wait=bool(wait)):
            pass

        child_config = parent_session.wait_for_next_event("debugpyAttach")
        parent_session.proceed()

        with debug.Session(child_config) as child_session:
            with child_session.start():
                child_session.set_breakpoints(child, all)

            if wait:
                # The child process should not have started running user code until
                # there was a client connection, so the breakpoint should be hit.
                child_session.wait_for_stop(
                    expected_frames=[some.dap.frame(child, line="bp")]
                )
                child_session.request_continue()
            else:
                # The breakpoint shouldn't be hit, since that line should have been
                # executed before we attached.
                pass

            backchannel.send("proceed")
            child_session.wait_for_terminated()


@pytest.mark.parametrize("run", runners.all_launch)
@pytest.mark.skipif(
    sys.platform != "win32", reason="job objects are specific to Windows"
)
def test_breakaway_job(pyfile, target, run):
    @pyfile
    def child():
        import os
        from debuggee import backchannel

        backchannel.send(os.getpid())
        backchannel.receive()
        backchannel.send("ok")

    @pyfile
    def parent():
        import debuggee
        import os
        import subprocess
        import sys

        debuggee.setup()
        argv = [sys.executable, sys.argv[1]]
        env = os.environ.copy()
        pipe_in = open(os.devnull, "r")
        pipe_out = open(os.devnull, "w")
        CREATE_BREAKAWAY_FROM_JOB = 0x01000000
        proc = subprocess.Popen(
            argv,
            env=env,
            stdin=pipe_in,
            stdout=pipe_out,
            stderr=pipe_out,
            creationflags=CREATE_BREAKAWAY_FROM_JOB,
        )
        pipe_in.close()
        pipe_out.close()
        proc.wait()

    with debug.Session() as parent_session:
        parent_session.config.update(
            {
                "redirectOutput": False,
                "subProcess": False,
            }
        )
        parent_session.expected_exit_code = some.int
        backchannel = parent_session.open_backchannel()

        with run(parent_session, target(parent, args=[child])):
            pass

        child_pid = backchannel.receive()
        child_process = psutil.Process(child_pid)

        parent_session.request("terminate")
        parent_session.wait_for_exit()

        # child should still be running
        backchannel.send("proceed")
        assert backchannel.receive() == "ok"

    log.info("Waiting for child process...")
    child_process.wait()


@pytest.mark.parametrize("run", runners.all_launch)
@pytest.mark.skipif(
    sys.platform == "win32", reason="os.exec() is specific to POSIX"
)
def test_subprocess_replace(pyfile, target, run):
    @pyfile
    def child():
        import os
        import sys

        assert "debugpy" in sys.modules

        from debuggee import backchannel

        backchannel.send(os.getpid())

    @pyfile
    def parent():
        import debuggee
        import os
        import sys

        debuggee.setup()
        print(f"execl({sys.executable!r}, {sys.argv[1]!r})")
        os.execl(sys.executable, sys.executable, sys.argv[1])

    with debug.Session() as parent_session:
        backchannel = parent_session.open_backchannel()
        with run(parent_session, target(parent, args=[child])):
            pass

        expected_child_config = expected_subprocess_config(parent_session)
        child_config = parent_session.wait_for_next_event("debugpyAttach")
        child_config.pop("isOutputRedirected", None)
        assert child_config == expected_child_config
        parent_session.proceed()

        with debug.Session(child_config) as child_session:
            with child_session.start():
                pass

            child_pid = backchannel.receive()
            assert child_pid == child_config["subProcessId"]
            assert str(child_pid) in child_config["name"]


@pytest.mark.parametrize("run", runners.all_launch)
def test_subprocess_with_parent_pid(pyfile, target, run):
    @pyfile
    def child():
        import sys

        assert "debugpy" in sys.modules

        import debugpy

        assert debugpy  # @bp

    @pyfile
    def parent():
        import debuggee
        import os
        import subprocess
        import sys

        import debugpy

        debuggee.setup()

        # Running it through a shell is necessary to ensure the
        # --parent-session-pid option is tested and the underlying
        # Python subprocess can associate with this one's debug session.
        if sys.platform == "win32":
            argv = ["cmd.exe", "/c"]
        else:
            argv = ["/bin/sh", "-c"]

        cli_opts = debugpy.get_cli_options()
        assert cli_opts, "No CLI options found"

        host, port = cli_opts.address
        access_token = cli_opts.adapter_access_token

        shell_args = [
            sys.executable,
            "-m",
            "debugpy",
            "--connect", f"{host}:{port}",
            "--parent-session-pid", str(os.getpid()),
            "--adapter-access-token", access_token,
            sys.argv[1],
        ]
        argv.append(" ".join(shell_args))

        subprocess.check_call(argv, env=os.environ | {"DEBUGPY_RUNNING": "false"})

    with debug.Session() as parent_session:
        with run(parent_session, target(parent, args=[child])):
            parent_session.set_breakpoints(child, all)

        with parent_session.wait_for_next_subprocess() as child_session:
            expected_child_config = expected_subprocess_config(parent_session)
            child_config = child_session.config
            child_config.pop("isOutputRedirected", None)
            assert child_config == expected_child_config

            with child_session.start():
                child_session.set_breakpoints(child, all)

            child_session.wait_for_stop(
                "breakpoint",
                expected_frames=[some.dap.frame(child, line="bp")],
            )
            child_session.request_continue()
