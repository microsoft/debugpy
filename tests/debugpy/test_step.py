# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, division, print_function, unicode_literals

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
