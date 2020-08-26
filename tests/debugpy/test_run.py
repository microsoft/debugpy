# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, division, print_function, unicode_literals

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


@pytest.mark.parametrize("run", runners.all_launch_terminal)
@pytest.mark.parametrize("python_args", ["", "-v"])
@pytest.mark.parametrize("python", ["", "custompy", "custompy -O"])
@pytest.mark.parametrize("python_key", ["python", "pythonPath"])
def test_custom_python(pyfile, run, target, python_key, python, python_args):
    @pyfile
    def code_to_debug():
        import sys
        import debuggee
        from debuggee import backchannel

        debuggee.setup()
        backchannel.send([sys.executable, sys.flags.optimize, sys.flags.verbose])

    python = python.split()
    python_args = python_args.split()
    python_cmd = (python if len(python) else [sys.executable]) + python_args

    class Session(debug.Session):
        def run_in_terminal(self, args, cwd, env):
            assert args[: len(python_cmd)] == python_cmd
            args[0] = sys.executable
            return super(Session, self).run_in_terminal(args, cwd, env)

    with Session() as session:
        session.config.pop("python", None)
        session.config.pop("pythonPath", None)
        if len(python):
            session.config[python_key] = python[0] if len(python) == 1 else python
        if len(python_args):
            session.config["pythonArgs"] = python_args

        backchannel = session.open_backchannel()
        with run(session, target(code_to_debug)):
            pass

        assert backchannel.receive() == [
            sys.executable,
            "-O" in python_cmd,
            "-v" in python_cmd,
        ]


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
