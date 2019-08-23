# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import pytest

from ptvsd.common import messaging
from tests import debug


expected_at_line = {
    "in_do_something": [
        {"label": "SomeClass", "type": "class", "start": 0, "length": 4},
        {"label": "someFunction", "type": "function", "start": 0, "length": 4},
        {"label": "someVariable", "type": "field", "start": 0, "length": 4},
    ],
    "in_some_function": [
        {"label": "SomeClass", "type": "class", "start": 0, "length": 4},
        {"label": "someFunction", "type": "function", "start": 0, "length": 4},
        {"label": "someVar", "type": "field", "start": 0, "length": 4},
        {"label": "someVariable", "type": "field", "start": 0, "length": 4},
    ],
    "done": [
        {"label": "SomeClass", "type": "class", "start": 0, "length": 4},
        {"label": "someFunction", "type": "function", "start": 0, "length": 4},
    ],
}


@pytest.mark.parametrize("bp_label", sorted(expected_at_line.keys()))
def test_completions_scope(pyfile, bp_label, start_method, run_as):
    @pyfile
    def code_to_debug():
        import debug_me  # noqa

        class SomeClass:
            def __init__(self, someVar):
                self.some_var = someVar

            def do_someting(self):
                someVariable = self.some_var
                return someVariable  # @in_do_something

        def someFunction(someVar):
            someVariable = someVar
            return SomeClass(someVariable).do_someting()  # @in_some_function

        someFunction("value")
        print("done")  # @done

    expected = expected_at_line[bp_label]

    with debug.Session(start_method) as session:
        session.configure(run_as, code_to_debug)

        session.set_breakpoints(code_to_debug, [code_to_debug.lines[bp_label]])
        session.start_debugging()

        hit = session.wait_for_stop(reason="breakpoint")
        resp_completions = session.send_request(
            "completions", arguments={"text": "some", "frameId": hit.frame_id, "column": 5}
        ).wait_for_response()
        targets = resp_completions.body["targets"]

        session.request_continue()

        targets.sort(key=lambda t: t["label"])
        expected.sort(key=lambda t: t["label"])
        assert targets == expected

        session.stop_debugging()


def test_completions_cases(pyfile, start_method, run_as):
    @pyfile
    def code_to_debug():
        import debug_me  # noqa

        a = 1
        b = {"one": 1, "two": 2}
        c = 3
        print([a, b, c])  # @break

    with debug.Session(start_method) as session:
        session.configure(run_as, code_to_debug)
        session.set_breakpoints(code_to_debug, [code_to_debug.lines["break"]])
        session.start_debugging()
        hit = session.wait_for_stop()

        response = session.send_request(
            "completions",
            arguments={"frameId": hit.frame_id, "text": "b.", "column": 3},
        ).wait_for_response()

        labels = set(target["label"] for target in response.body["targets"])
        assert labels.issuperset(
            ["get", "items", "keys", "setdefault", "update", "values"]
        )

        response = session.send_request(
            "completions",
            arguments={
                "frameId": hit.frame_id,
                "text": "x = b.setdefault",
                "column": 13,
            },
        ).wait_for_response()

        assert response.body["targets"] == [
            {"label": "setdefault", "length": 6, "start": 6, "type": "function"}
        ]

        response = session.send_request(
            "completions",
            arguments={"frameId": hit.frame_id, "text": "not_there", "column": 10},
        ).wait_for_response()

        assert not response.body["targets"]

        # Check errors
        with pytest.raises(messaging.MessageHandlingError) as error:
            response = session.send_request(
                "completions",
                arguments={
                    "frameId": 9999999,  # frameId not available.
                    "text": "not_there",
                    "column": 10,
                },
            ).wait_for_response()
        assert "Wrong ID sent from the client:" in str(error)

        session.request_continue()
        session.stop_debugging()
