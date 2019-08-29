# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import pytest

from tests import debug
from tests.patterns import some
from tests.timeline import Event


def test_set_next_statement(pyfile, start_method, run_as):
    @pyfile
    def code_to_debug():
        import debug_me  # noqa

        def func():
            print(1)  # @inner1
            print(2)  # @inner2

        print(3)  # @outer3
        func()

    line_numbers = code_to_debug.lines

    with debug.Session(start_method) as session:
        session.configure(run_as, code_to_debug)
        session.set_breakpoints(code_to_debug, [line_numbers["inner1"]])
        session.start_debugging()

        hit = session.wait_for_stop()
        line = hit.frames[0]["line"]
        assert line == line_numbers["inner1"]

        targets = (
            session.send_request(
                "gotoTargets",
                {"source": {"path": code_to_debug}, "line": line_numbers["outer3"]},
            )
            .wait_for_response()
            .body["targets"]
        )

        assert targets == [
            {"id": some.number, "label": some.str, "line": line_numbers["outer3"]}
        ]
        outer3_target = targets[0]["id"]

        with pytest.raises(Exception):
            session.send_request(
                "goto", {"threadId": hit.thread_id, "targetId": outer3_target}
            ).wait_for_response()

        targets = (
            session.send_request(
                "gotoTargets",
                {"source": {"path": code_to_debug}, "line": line_numbers["inner2"]},
            )
            .wait_for_response()
            .body["targets"]
        )

        assert targets == [
            {"id": some.number, "label": some.str, "line": line_numbers["inner2"]}
        ]
        inner2_target = targets[0]["id"]

        session.send_request(
            "goto", {"threadId": hit.thread_id, "targetId": inner2_target}
        ).wait_for_response()

        session.wait_for_next(Event("continued"))

        hit = session.wait_for_stop(reason="goto")
        line = hit.frames[0]["line"]
        assert line == line_numbers["inner2"]

        session.send_request("continue").wait_for_response()
