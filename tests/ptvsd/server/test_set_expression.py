# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

from tests import debug
from tests.patterns import some


def test_set_expression(pyfile, start_method, run_as):
    @pyfile
    def code_to_debug():
        from debug_me import backchannel
        import ptvsd

        a = 1
        ptvsd.break_into_debugger()
        backchannel.write_json(a)

    with debug.Session() as session:
        session.initialize(
            target=(run_as, code_to_debug),
            start_method=start_method,
            use_backchannel=True,
        )
        session.start_debugging()
        hit = session.wait_for_thread_stopped()

        resp_scopes = session.send_request(
            "scopes", arguments={"frameId": hit.frame_id}
        ).wait_for_response()
        scopes = resp_scopes.body["scopes"]
        assert len(scopes) > 0

        resp_variables = session.send_request(
            "variables",
            arguments={"variablesReference": scopes[0]["variablesReference"]},
        ).wait_for_response()
        variables = list(
            v for v in resp_variables.body["variables"] if v["name"] == "a"
        )
        assert variables == [
            {
                "type": "int",
                "value": "1",
                "name": "a",
                "evaluateName": "a",
                "variablesReference": 0,
            }
        ]

        resp_set_variable = session.send_request(
            "setExpression",
            arguments={"frameId": hit.frame_id, "expression": "a", "value": "1000"},
        ).wait_for_response()
        assert resp_set_variable.body == some.dict.containing(
            {"type": "int", "value": "1000"}
        )

        session.send_request("continue").wait_for_response(freeze=False)

        assert session.read_json() == 1000

        session.wait_for_exit()
