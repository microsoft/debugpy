import os
import os.path
from textwrap import dedent

import ptvsd
from ptvsd.wrapper import INITIALIZE_RESPONSE  # noqa
from tests.helpers.debugclient import EasyDebugClient as DebugClient
from tests.helpers.debugsession import Awaitable

from . import (
    LifecycleTestsBase,
    lifecycle_handshake,
)


ROOT = os.path.dirname(os.path.dirname(ptvsd.__file__))
PORT = 9876
CONNECT_TIMEOUT = 3.0


class VariableLifecycleTests(LifecycleTestsBase):

    def test_variables(self):
        source = dedent("""
            a = 1
            b = {"one":1, "two":2}
            # <Token>
            c = 3
            """)
        (filename, filepath, env, expected_module, argv,
         cwd) = self.get_test_info(source)

        bp_line = self.find_line(filepath, 'Token')
        breakpoints = [{
            "source": {
                "path": filepath
            },
            "breakpoints": [{
                "line": bp_line
            }]
        }]

        with DebugClient(port=PORT, connecttimeout=CONNECT_TIMEOUT) as editor:
            adapter, session = editor.host_local_debugger(
                argv, env=env, cwd=cwd, timeout=CONNECT_TIMEOUT)

            terminated = session.get_awaiter_for_event('terminated')
            exited = session.get_awaiter_for_event('exited')
            thread_exit = session.get_awaiter_for_event('thread', lambda msg: msg.body.get("reason", "") == "exited") # noqa

            with session.wait_for_event("stopped") as result:
                (
                    _,
                    _,
                    _,
                    _,
                    _,
                    _,
                ) = lifecycle_handshake(
                    session, "launch", breakpoints=breakpoints)
            tid = result["msg"].body["threadId"]

            stacktrace = session.send_request("stackTrace", threadId=tid)
            stacktrace.wait()
            frame_id = stacktrace.resp.body["stackFrames"][0]["id"]
            scopes = session.send_request('scopes', frameId=frame_id)
            scopes.wait()
            variables_reference = scopes.resp.body["scopes"][0]["variablesReference"] # noqa
            variables = session.send_request('variables', variablesReference=variables_reference) # noqa
            variables.wait()

            var_b = list(b for b in variables.resp.body["variables"] if b["name"] == "b") # noqa
            var_b = var_b[0] if len(var_b) == 1 else None
            if var_b is None:
                var_b_variables = None
            else:
                var_b_ref = var_b["variablesReference"]
                var_b_variables = session.send_request('variables', variablesReference=var_b_ref) # noqa
                var_b_variables.wait()

            var_a_evaluate = session.send_request('evaluate',
                                                  expression="a",
                                                  frameId=frame_id)
            var_b_one_evaluate = session.send_request('evaluate',
                                                      expression="b['one']", # noqa
                                                      frameId=frame_id)

            Awaitable.wait_all(var_a_evaluate, var_b_one_evaluate)

            continued = session.get_awaiter_for_event('continued')
            session.send_request("continue", threadId=tid)

            Awaitable.wait_all(terminated, exited, thread_exit, continued)
            adapter.wait()

        # Variables for a, b, __file__, __main__
        self.assertGreaterEqual(len(variables.resp.body["variables"]), 3)
        expected_variables = [
                                {
                                    "name": "a",
                                    "type": "int",
                                    "value": "1",
                                    "evaluateName": "a"
                                },
                                {
                                    "name": "b",
                                    "type": "dict",
                                    "value": "{'one': 1, 'two': 2}",
                                    "evaluateName": "b"
                                },
                                {
                                    "name": "__builtins__",
                                    "type": "dict",
                                    "evaluateName": "__builtins__"
                                },
                                {
                                    "name": "__doc__",
                                    "type": "NoneType",
                                    "value": "None",
                                    "evaluateName": "__doc__"
                                },
                                {
                                    "name": "__file__",
                                    "type": "str",
                                    "presentationHint": {
                                        "attributes": [
                                            "rawString"
                                        ]
                                    },
                                    "evaluateName": "__file__"
                                },
                                {
                                    "name": "__loader__",
                                    "type": "SourceFileLoader",
                                    "evaluateName": "__loader__"
                                },
                                {
                                    "name": "__name__",
                                    "type": "str",
                                    "value": "'__main__'",
                                    "presentationHint": {
                                        "attributes": ["rawString"]
                                    },
                                    "evaluateName": "__name__"
                                },
                                {
                                    "name": "__package__",
                                    "type": "NoneType",
                                    "value": "None",
                                    "evaluateName": "__package__"
                                },
                                {
                                    "name": "__spec__",
                                    "type": "NoneType",
                                    "value": "None",
                                    "evaluateName": "__spec__"
                                }
                            ]
        self.assert_is_subset(variables.resp.body["variables"], expected_variables) # noqa
        expected_var_a_eval = {"type": "int", "result": "1"}
        var_a_evaluate.resp.body == expected_var_a_eval

        assert var_b_variables is not None
        expected_var_b = {
                            "variables": [
                                {
                                    "type": "int",
                                    "value": "1",
                                    "evaluateName": "b['one']"
                                },
                                {
                                    "type": "int",
                                    "value": "2",
                                    "evaluateName": "b['two']"
                                },
                                {
                                    "name": "__len__",
                                    "type": "int",
                                    "value": "2",
                                    "evaluateName": "b.__len__"
                                }
                            ]
                        }
        self.assert_is_subset(var_b_variables.resp.body, expected_var_b) # noqa

        expected_var_b_eval = {"type": " int", "result": "1"}
        var_b_one_evaluate.resp.body == expected_var_b_eval
