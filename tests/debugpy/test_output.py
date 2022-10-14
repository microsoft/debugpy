# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import pytest
import sys

from tests import debug
from tests.debug import runners

# When debuggee exits, there's no guarantee currently that all "output" events have
# already been sent. To ensure that they are, all tests below must set a breakpoint
# on the last line of the debuggee, and stop on it. Since debugger sends its events
# sequentially, by the time we get to "stopped", we also have all the output events.


@pytest.mark.parametrize("run", runners.all)
def test_with_no_output(pyfile, target, run):
    @pyfile
    def code_to_debug():
        import debuggee

        debuggee.setup()
        ()  # @wait_for_output

    with debug.Session() as session:
        session.config["redirectOutput"] = True

        with run(session, target(code_to_debug)):
            session.set_breakpoints(code_to_debug, all)

        session.wait_for_stop("breakpoint")
        session.request_continue()

    output = session.output("stdout")
    lines = []
    for line in output.splitlines(keepends=True):
        if not line.startswith("Attaching to PID:"):
            lines.append(line)
    
    output = "".join(lines)
    
    assert not output
    assert not session.output("stderr")
    if session.debuggee is not None:
        assert not session.captured_stdout()
        assert not session.captured_stderr()


def test_with_tab_in_output(pyfile, target, run):
    @pyfile
    def code_to_debug():
        import debuggee

        debuggee.setup()
        a = "\t".join(("Hello", "World"))
        print(a)
        ()  # @wait_for_output

    with debug.Session() as session:
        session.config["redirectOutput"] = True

        with run(session, target(code_to_debug)):
            session.set_breakpoints(code_to_debug, all)

        session.wait_for_stop()
        session.request_continue()

    assert session.output("stdout").startswith("Hello\tWorld")


@pytest.mark.parametrize("redirect_mode", ["internalConsole", "redirectOutput"])
def test_redirect_output_and_eval(pyfile, target, run, redirect_mode):
    @pyfile
    def code_to_debug():
        import debuggee
        import sys

        debuggee.setup()
        sys.stdout.write("line\n")
        ()  # @wait_for_output

    with debug.Session() as session:
        if redirect_mode == "redirectOutput":
            session.config["redirectOutput"] = True
        elif redirect_mode == "internalConsole":
            session.config["console"] = "internalConsole"
        else:
            raise AssertionError("Unexpected: " + redirect_mode)

        with run(session, target(code_to_debug)):
            session.set_breakpoints(code_to_debug, all)

        stop = session.wait_for_stop()
        session.request(
            "evaluate",
            {
                "expression": "sys.stdout.write('evaluated\\n')",
                "frameId": stop.frame_id,
                "context": "repl",
            },
        )

        session.request_continue()

    assert session.output("stdout") == "line\nevaluated\n"


@pytest.mark.parametrize("run", runners.all)
@pytest.mark.parametrize("redirect", ["enabled", "disabled"])
def test_redirect_output(pyfile, target, run, redirect):
    @pyfile
    def code_to_debug():
        import debuggee

        debuggee.setup()
        for i in [111, 222, 333, 444]:
            print(i)

        ()  # @wait_for_output

    with debug.Session() as session:
        session.config["redirectOutput"] = redirect == "enabled"

        with run(session, target(code_to_debug)):
            session.set_breakpoints(code_to_debug, all)

        session.wait_for_stop()
        session.request_continue()

    output = session.output("stdout")
    lines = []
    for line in output.splitlines(keepends=True):
        if not line.startswith("Attaching to PID:"):
            lines.append(line)
    
    output = "".join(lines)
    if redirect == "enabled":
        assert output == "111\n222\n333\n444\n"
    else:
        assert not output


def test_non_ascii_output(pyfile, target, run):
    @pyfile
    def code_to_debug():
        import debuggee
        import sys

        debuggee.setup()
        a = b"\xc3\xa9 \xc3\xa0 \xc3\xb6 \xc3\xb9\n"
        sys.stdout.buffer.write(a)
        ()  # @wait_for_output

    with debug.Session() as session:
        session.config["redirectOutput"] = True

        with run(session, target(code_to_debug)):
            session.set_breakpoints(code_to_debug, all)

        session.wait_for_stop()
        session.request_continue()

    output = session.output("stdout").encode("utf-8", "replace")

    assert output in (
        b"\xc3\xa9 \xc3\xa0 \xc3\xb6 \xc3\xb9\n",
        b"\xc3\x83\xc2\xa9 \xc3\x83\xc2\xa0 \xc3\x83\xc2\xb6 \xc3\x83\xc2\xb9\n",
    )


if sys.platform == "win32":

    @pytest.mark.parametrize("redirect_output", ["", "redirect_output"])
    def test_pythonw_output(pyfile, target, run, redirect_output):
        @pyfile
        def code_to_debug():
            import debuggee

            debuggee.setup()
            print("ok")
            ()  # @wait_for_output

        with debug.Session() as session:
            # Don't capture launcher output - we want to see how it handles not
            # having sys.stdin and sys.stdout available.
            session.captured_output = set()

            session.config["pythonPath"] = sys.executable + "/../pythonw.exe"
            session.config["redirectOutput"] = bool(redirect_output)

            with run(session, target(code_to_debug)):
                session.set_breakpoints(code_to_debug, all)

            session.wait_for_stop()
            session.request_continue()

        assert session.output("stdout") == ("ok\n" if redirect_output else "")
