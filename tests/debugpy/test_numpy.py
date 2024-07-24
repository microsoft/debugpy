# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from tests import debug
from tests.patterns import some


def test_ndarray(pyfile, target, run):
    @pyfile
    def code_to_debug():
        import numpy
        import debuggee

        debuggee.setup()
        a = numpy.array([123, 456], numpy.int32)
        print(a)  # @bp

    with debug.Session() as session:
        session.config["variablePresentation"] = {"all": "hide", "protected": "inline"}
        with run(session, target(code_to_debug)):
            session.set_breakpoints(code_to_debug, all)

        stop = session.wait_for_stop()
        scopes = session.request("scopes", {"frameId": stop.frame_id})["scopes"]
        globals_ref = scopes[0]["variablesReference"]
        vars = session.request(
            "variables",
            {"variablesReference": globals_ref},
        )["variables"]
        print(vars)

        # Fetch children variables of the array.
        (a,) = (v for v in vars if v["name"] == "a")
        a_vars = session.request(
            "variables",
            {"variablesReference": a["variablesReference"]},
        )["variables"]
        print(a_vars)

        # Fetch the actual array items
        (items,) = (v for v in a_vars if v["name"] == "[0:2] ")
        a_items = session.request(
            "variables",
            {"variablesReference": items["variablesReference"]},
        )["variables"]
        print(a_items)

        assert a_items == [
            some.dict.containing(
                {
                    "type": "int32",
                    "name": "0",
                    "value": some.str.containing("123"),
                    "variablesReference": some.int,
                }
            ),
            some.dict.containing(
                {
                    "type": "int32",
                    "name": "1",
                    "value": some.str.containing("456"),
                    "variablesReference": some.int,
                }
            ),
            some.dict.containing(
                {
                    "type": "int",
                    "name": "len()",
                    "value": "2",
                    "presentationHint": {"attributes": ["readOnly"]},
                    "variablesReference": 0,
                }
            ),
        ]

        session.request_continue()
