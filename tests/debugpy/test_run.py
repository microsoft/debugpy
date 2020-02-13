# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, division, print_function, unicode_literals

import os
import pytest
import re
import sys
import time

import debugpy
from debugpy.common import log, messaging
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
        session.config.env["PATH"] = tmpdir.strpath + ":" + os.environ["PATH"]

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


@pytest.mark.parametrize(
    # Can't test "internalConsole", because we don't have debuggee stdin to press the key.
    "run",
    [runners.launch["integratedTerminal"], runners.launch["externalTerminal"]],
)
@pytest.mark.parametrize("exit_code", [0, 42])
@pytest.mark.parametrize("wait_on_normal", ["", "wait_on_normal"])
@pytest.mark.parametrize("wait_on_abnormal", ["", "wait_on_abnormal"])
@pytest.mark.parametrize(
    "process_lifetime",
    ["run_to_completion", "request_terminate", "request_disconnect", "drop_connection"],
)
def test_wait_on_exit(
    pyfile, target, run, exit_code, wait_on_normal, wait_on_abnormal, process_lifetime
):
    @pyfile
    def code_to_debug():
        import sys

        import debuggee
        import debugpy

        debuggee.setup()
        debugpy.breakpoint()
        print()  # line on which it'll actually break
        sys.exit(int(sys.argv[1]))

    expect_wait = (process_lifetime == "run_to_completion") and (
        (wait_on_normal and exit_code == 0) or (wait_on_abnormal and exit_code != 0)
    )

    with debug.Session() as session:
        session.expected_exit_code = (
            None if process_lifetime == "drop_connection" else some.int
        )
        if wait_on_normal:
            session.config["waitOnNormalExit"] = True
        if wait_on_abnormal:
            session.config["waitOnAbnormalExit"] = True

        with run(session, target(code_to_debug, args=[str(exit_code)])):
            pass

        session.wait_for_stop()
        if process_lifetime == "run_to_completion":
            session.request_continue()
        elif process_lifetime == "request_terminate":
            session.request("terminate", freeze=False)
        elif process_lifetime == "request_disconnect":
            session.disconnect()
        elif process_lifetime == "drop_connection":
            session.disconnect(force=True)
        else:
            pytest.fail(process_lifetime)

        def has_waited():
            lines = session.captured_output.stdout_lines()
            return any(
                s == some.bytes.matching(br"Press .* to continue . . .\s*")
                for s in lines
            )

        if expect_wait:
            log.info("Waiting for keypress prompt...")
            while not has_waited():
                time.sleep(0.1)

            # Wait a bit to simulate the user reaction time, and test that debuggee does
            # not exit all by itself.
            time.sleep(1)
            assert session.debuggee.poll() is None

            log.info("Simulating keypress.")
            session.debuggee.stdin.write(b"\n")

        else:
            session.debuggee.wait()
            assert not has_waited()
