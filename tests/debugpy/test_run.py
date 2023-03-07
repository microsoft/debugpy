# coding: utf-8
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import os
import pytest
import re
import sys

import debugpy
from debugpy.common import messaging
from tests import debug, test_data, timeline
from tests.debug import runners, targets
from tests.patterns import some


@pytest.mark.parametrize("run", runners.all)
@pytest.mark.parametrize("target", targets.all)
def test_run(pyfile, target, run):
    @pyfile
    def code_to_debug():
        import os
        import sys

        import debuggee
        from debuggee import backchannel

        debuggee.setup()
        print("begin")
        backchannel.send(os.path.abspath(sys.modules["debugpy"].__file__))
        assert backchannel.receive() == "continue"
        print("end")

    with debug.Session() as session:
        backchannel = session.open_backchannel()
        with run(session, target(code_to_debug)):
            pass

        expected_debugpy_path = os.path.abspath(debugpy.__file__)
        assert backchannel.receive() == some.str.matching(
            re.escape(expected_debugpy_path) + r"(c|o)?"
        )

        backchannel.send("continue")
        session.wait_for_next_event("terminated")
        session.proceed()


@pytest.mark.parametrize("run", [runners.launch["internalConsole"]])
def test_run_relative_path(pyfile, run):
    @pyfile
    def code_to_debug():
        import debuggee
        from debuggee import backchannel
        from _pydev_bundle.pydev_log import list_log_files

        debuggee.setup()
        from _pydevd_bundle import pydevd_constants  # @ bp1

        backchannel.send(
            list_log_files(pydevd_constants.DebugInfoHolder.PYDEVD_DEBUG_FILE)
        )
        assert backchannel.receive() == "continue"

    with debug.Session() as session:
        backchannel = session.open_backchannel()
        code_to_debug = str(code_to_debug)
        cwd = os.path.dirname(os.path.dirname(code_to_debug))

        program = targets.Program(code_to_debug)
        program.make_relative(cwd)
        with run(session, program):
            session.set_breakpoints(code_to_debug, all)

        session.wait_for_stop()
        session.request_continue()

        pydevd_debug_files = backchannel.receive()
        backchannel.send("continue")
        session.wait_for_next_event("terminated")
        session.proceed()

    # Check if we don't have errors in the pydevd log (the
    # particular error this test is covering:
    # https://github.com/microsoft/debugpy/issues/620
    # is handled by pydevd but produces a Traceback in the logs).
    for pydevd_debug_file in pydevd_debug_files:
        with open(pydevd_debug_file, "r") as stream:
            contents = stream.read()

    assert "FileNotFound" not in contents


@pytest.mark.parametrize("run", runners.all_launch)
def test_run_submodule(run):
    with debug.Session() as session:
        session.config["cwd"] = test_data / "testpkgs"

        backchannel = session.open_backchannel()
        with run(session, targets.Module(name="pkg1.sub")):
            pass

        assert backchannel.receive() == "ok"


@pytest.mark.parametrize("run", runners.all_launch)
@pytest.mark.parametrize("target", targets.all)
def test_nodebug(pyfile, run, target):
    @pyfile
    def code_to_debug():
        import debuggee
        from debuggee import backchannel

        debuggee.setup()
        backchannel.receive()  # @ bp1
        print("ok")  # @ bp2

    with debug.Session() as session:
        session.config["noDebug"] = True
        session.config["redirectOutput"] = True

        backchannel = session.open_backchannel()
        run(session, target(code_to_debug))

        with pytest.raises(messaging.MessageHandlingError):
            session.set_breakpoints(code_to_debug, all)

        backchannel.send(None)

        # Breakpoint shouldn't be hit.
        pass

    assert "ok" in session.output("stdout")


@pytest.mark.skipif(sys.platform == "win32", reason="sudo not available on Windows")
@pytest.mark.parametrize("run", runners.all_launch)
def test_sudo(pyfile, tmpdir, run, target):
    # Since the test can't rely on sudo being allowed for the user, create a dummy
    # sudo script that doesn't actually elevate, but sets an environment variable
    # that can be checked in the debuggee.
    sudo = tmpdir / "sudo"
    sudo.write(
        """#!/bin/sh
        if [ "$1" = "-E" ]; then shift; fi
        exec env DEBUGPY_SUDO=1 "$@"
        """
    )
    os.chmod(sudo.strpath, 0o777)

    @pyfile
    def code_to_debug():
        import os

        import debuggee
        from debuggee import backchannel

        debuggee.setup()
        backchannel.send(os.getenv("DEBUGPY_SUDO", "0"))

    with debug.Session() as session:
        session.config["sudo"] = True
        session.spawn_adapter.env["PATH"] = session.spawn_debuggee.env["PATH"] = (
            tmpdir.strpath + ":" + os.environ["PATH"]
        )

        backchannel = session.open_backchannel()
        with run(session, target(code_to_debug)):
            pass

        # The "runInTerminal" request sent by the adapter to spawn the launcher,
        # if any, shouldn't be using sudo.
        assert all(
            "sudo" not in req.arguments["args"]
            for req in session.all_occurrences_of(timeline.Request("runInTerminal"))
        )

        # The launcher, however, should use our dummy sudo to spawn the debuggee,
        # and the debuggee should report the environment variable accordingly.
        assert backchannel.receive() == "1"


def make_custompy(tmpdir, id=""):
    if sys.platform == "win32":
        custompy = tmpdir / ("custompy" + id + ".cmd")
        script = """@echo off
            set DEBUGPY_CUSTOM_PYTHON=<id>;%DEBUGPY_CUSTOM_PYTHON%
            <python> %*
            """
    else:
        custompy = tmpdir / ("custompy" + id + ".sh")
        script = """#!/bin/sh
            env "DEBUGPY_CUSTOM_PYTHON=<id>;$DEBUGPY_CUSTOM_PYTHON" <python> "$@"
            """

    script = script.replace("<id>", id)
    script = script.replace("<python>", sys.executable)
    custompy.write(script)
    os.chmod(custompy.strpath, 0o777)

    return custompy.strpath


@pytest.mark.parametrize("run", runners.all_launch)
@pytest.mark.parametrize("debuggee_custompy", [None, "launcher"])
@pytest.mark.parametrize("launcher_custompy", [None, "debuggee"])
def test_custom_python(
    pyfile, tmpdir, run, target, debuggee_custompy, launcher_custompy
):
    @pyfile
    def code_to_debug():
        import os

        import debuggee
        from debuggee import backchannel

        debuggee.setup()
        backchannel.send(os.getenv("DEBUGPY_CUSTOM_PYTHON"))

    expected = ""
    if debuggee_custompy:
        debuggee_custompy = make_custompy(tmpdir, "debuggee")
        expected += "debuggee;"
    if launcher_custompy:
        launcher_custompy = make_custompy(tmpdir, "launcher")
        expected += "launcher;"
    else:
        # If "python" is set, it also becomes the default for "debugLauncherPython"
        expected *= 2
    if not len(expected):
        pytest.skip()

    with debug.Session() as session:
        session.config.pop("python", None)
        if launcher_custompy:
            session.config["debugLauncherPython"] = launcher_custompy
        if debuggee_custompy:
            session.config["python"] = debuggee_custompy

        backchannel = session.open_backchannel()
        with run(session, target(code_to_debug)):
            pass

        assert backchannel.receive() == expected


@pytest.mark.parametrize("run", runners.all_launch)
@pytest.mark.parametrize("python_args", [None, "-B"])
@pytest.mark.parametrize("python", [None, "custompy", "custompy,-O"])
@pytest.mark.parametrize("python_key", ["python", "pythonPath"])
def test_custom_python_args(
    pyfile, tmpdir, run, target, python_key, python, python_args
):
    @pyfile
    def code_to_debug():
        import sys

        import debuggee
        from debuggee import backchannel

        debuggee.setup()
        backchannel.send([sys.flags.optimize, sys.flags.dont_write_bytecode])

    custompy = make_custompy(tmpdir)
    python = [] if python is None else python.split(",")
    python = [(custompy if arg == "custompy" else arg) for arg in python]
    python_args = [] if python_args is None else python_args.split(",")
    python_cmd = (python if len(python) else [sys.executable]) + python_args

    with debug.Session() as session:
        session.config.pop("python", None)
        session.config.pop("pythonPath", None)
        if len(python):
            session.config[python_key] = python[0] if len(python) == 1 else python
        if len(python_args):
            session.config["pythonArgs"] = python_args

        backchannel = session.open_backchannel()
        with run(session, target(code_to_debug)):
            pass

        assert backchannel.receive() == ["-O" in python_cmd, "-B" in python_cmd]


@pytest.mark.parametrize("run", runners.all)
@pytest.mark.parametrize("target", targets.all)
@pytest.mark.parametrize("frame_eval", ["", "yes", "no"])
def test_frame_eval(pyfile, target, run, frame_eval):
    # Frame-eval optimizations are not available for some Python implementations,
    # but pydevd will still try to use them if the environment variable is set to
    # "yes" explicitly, so the test must detect and skip those cases.
    if frame_eval == "yes":
        try:
            import _pydevd_frame_eval.pydevd_frame_eval_cython_wrapper  # noqa
        except ImportError:
            pytest.skip("Frame-eval not available")
        else:
            pass

    @pyfile
    def code_to_debug():
        import debuggee
        from debuggee import backchannel

        debuggee.setup()

        from _pydevd_frame_eval.pydevd_frame_eval_main import USING_FRAME_EVAL

        backchannel.send(USING_FRAME_EVAL)

    with debug.Session() as session:
        assert "PYDEVD_USE_FRAME_EVAL" not in os.environ
        if len(frame_eval):
            env = (
                session.config.env
                if run.request == "launch"
                else session.spawn_debuggee.env
            )
            env["PYDEVD_USE_FRAME_EVAL"] = frame_eval

        backchannel = session.open_backchannel()
        with run(session, target(code_to_debug)):
            pass

        using_frame_eval = backchannel.receive()
        assert using_frame_eval == (frame_eval == "yes")


@pytest.mark.parametrize("run", [runners.all_launch[0]])
def test_unicode_dir(tmpdir, run, target):
    unicode_chars = "á"

    directory = os.path.join(str(tmpdir), unicode_chars)
    os.makedirs(directory)

    code_to_debug = os.path.join(directory, "experiment.py")
    with open(code_to_debug, "wb") as stream:
        stream.write(
            b"""
import debuggee
from debuggee import backchannel

debuggee.setup()
backchannel.send('ok')
"""
        )

    with debug.Session() as session:
        backchannel = session.open_backchannel()
        with run(session, target(code_to_debug)):
            pass

        received = backchannel.receive()
        assert received == "ok"
