# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import pytest

from tests import debug
from tests.patterns import some


def test_set_next_statement(pyfile, run, target):
    @pyfile
    def code_to_debug():
        import debuggee

        debuggee.setup()

        def func():
            print(1)  # @inner1
            print(2)  # @inner2

        print(3)  # @outer3
        func()

    line_numbers = code_to_debug.lines

    with debug.Session() as session:
        with run(session, target(code_to_debug)):
            session.set_breakpoints(code_to_debug, ["inner1"])

        stop = session.wait_for_stop(
            expected_frames=[some.dap.frame(code_to_debug, "inner1")]
        )

        targets = session.request(
            "gotoTargets",
            {"source": {"path": code_to_debug}, "line": line_numbers["outer3"]},
        )["targets"]
        assert targets == [
            {"id": some.number, "label": some.str, "line": line_numbers["outer3"]}
        ]
        outer3_target = targets[0]["id"]

        with pytest.raises(Exception):
            session.request(
                "goto", {"threadId": stop.thread_id, "targetId": outer3_target}
            )

        targets = session.request(
            "gotoTargets",
            {"source": {"path": code_to_debug}, "line": line_numbers["inner2"]},
        )["targets"]
        assert targets == [
            {"id": some.number, "label": some.str, "line": line_numbers["inner2"]}
        ]
        inner2_target = targets[0]["id"]

        session.request("goto", {"threadId": stop.thread_id, "targetId": inner2_target})
        session.wait_for_next_event("continued")

        stop = session.wait_for_stop(
            "goto", expected_frames=[some.dap.frame(code_to_debug, "inner2")]
        )
        session.request_continue()


@pytest.mark.parametrize(
    "break_at, steps",
    [
        ("raise", [("stepOut", "call_thrower")]),
        ("raise", [("next", "finally")]),
        ("finally", [("next", "except")]),
        ("finally", [("stepOut", "call_cleanup_thrower")]),
        ("call_thrower", [("next", "finally"), ("next", "except")]),
    ],
)
@pytest.mark.parametrize("exception_filters", [["uncaught"], []])
def test_step_frame_exited_by_exception(
    pyfile, target, run, break_at, steps, exception_filters
):
    # A step whose frame is left by an exception must stop in the next frame that runs.
    @pyfile
    def code_to_debug():
        import debuggee

        debuggee.setup()

        def thrower(i):
            raise ValueError(i)  # @raise

        def cleanup_thrower(i):
            try:
                thrower(i)  # @call_thrower
            finally:
                print("finally", i)  # @finally

        def via_throw(i):
            try:
                cleanup_thrower(i)  # @call_cleanup_thrower
            except ValueError:  # @except
                return i * 2
            return -1

        for i in range(3):
            print("call", i, "->", via_throw(i))

    with debug.Session() as session:
        with run(session, target(code_to_debug)):
            session.request("setExceptionBreakpoints", {"filters": exception_filters})
            # Only stop in the second call: an unconditional breakpoint would be hit
            # again in the next iteration, which would hide a step that never stops.
            session.request(
                "setBreakpoints",
                {
                    "source": {"path": code_to_debug},
                    "breakpoints": [
                        {"line": code_to_debug.lines[break_at], "condition": "i == 1"}
                    ],
                },
            )

        stop = session.wait_for_stop(
            "breakpoint", expected_frames=[some.dap.frame(code_to_debug, break_at)]
        )
        for step, expected_line in steps:
            session.request(step, {"threadId": stop.thread_id})
            stop = session.wait_for_stop(
                "step", expected_frames=[some.dap.frame(code_to_debug, expected_line)]
            )
            # Still in the call that hit the breakpoint.
            assert session.get_variable("i", frame_id=stop.frame_id)["value"] == "1"

        session.request_continue()
