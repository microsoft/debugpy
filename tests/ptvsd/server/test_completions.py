# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, division, print_function, unicode_literals

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


@pytest.mark.parametrize("line", sorted(expected_at_line.keys()))
def test_completions_scope(pyfile, line, target, run):
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

    expected = sorted(expected_at_line[line], key=lambda t: t["label"])

    with debug.Session() as session:
        with run(session, target(code_to_debug)):
            session.set_breakpoints(code_to_debug, [code_to_debug.lines[line]])

        stop = session.wait_for_stop("breakpoint")
        completions = session.request(
            "completions", {"text": "some", "frameId": stop.frame_id, "column": 5}
        )
        targets = sorted(completions["targets"], key=lambda t: t["label"])
        assert targets == expected

        session.request_continue()


def test_completions_cases(pyfile, target, run):
    @pyfile
    def code_to_debug():
        import debug_me  # noqa

        a = 1
        b = {"one": 1, "two": 2}
        c = 3
        print([a, b, c])  # @break

    with debug.Session() as session:
        with run(session, target(code_to_debug)):
            session.set_breakpoints(code_to_debug, [code_to_debug.lines["break"]])

        stop = session.wait_for_stop()

        completions = session.request(
            "completions", {"frameId": stop.frame_id, "text": "b.", "column": 3}
        )
        labels = set(target["label"] for target in completions["targets"])
        assert labels >= {"get", "items", "keys", "setdefault", "update", "values"}

        completions = session.request(
            "completions",
            {"frameId": stop.frame_id, "text": "x = b.setdefault", "column": 13},
        )
        assert completions["targets"] == [
            {"label": "setdefault", "length": 6, "start": 6, "type": "function"}
        ]

        completions = session.request(
            "completions", {"frameId": stop.frame_id, "text": "not_there", "column": 10}
        )
        assert not completions["targets"]

        with pytest.raises(messaging.MessageHandlingError):
            completions = session.request(
                "completions",
                {
                    "frameId": 9999999,  # nonexistent frameId
                    "text": "not_there",
                    "column": 10,
                },
            )

        session.request_continue()
