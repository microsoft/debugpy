# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import pytest

from tests import debug, timeline
from tests.patterns import some


def test_evaluate(pyfile, target, run):
    @pyfile
    def code_to_debug():
        import debuggee

        debuggee.setup()
        a = 1
        b = {"one": 1, 2: "two"}
        print(a, b)  # @bp

    with debug.Session() as session:
        with run(session, target(code_to_debug)):
            session.set_breakpoints(code_to_debug, all)

        stop = session.wait_for_stop()

        # Evaluate a variable name.
        evaluate1 = session.request(
            "evaluate", {"expression": "a", "frameId": stop.frame_id}
        )
        assert evaluate1 == some.dict.containing({"type": "int", "result": "1"})

        # Evaluate dict indexing.
        evaluate2 = session.request(
            "evaluate", {"expression": "b[2]", "frameId": stop.frame_id}
        )
        assert evaluate2 == some.dict.containing({"type": "str", "result": "'two'"})

        # Evaluate an expression with a binary operator.
        evaluate3 = session.request(
            "evaluate", {"expression": 'a + b["one"]', "frameId": stop.frame_id}
        )
        assert evaluate3 == some.dict.containing({"type": "int", "result": "2"})

        session.request_continue()


def test_variables(pyfile, target, run):
    @pyfile
    def code_to_debug():
        import debuggee

        debuggee.setup()
        a = 1
        b = {"one": 1, 2: "two"}
        c = 3
        print([a, b, c])  # @bp

    with debug.Session() as session:
        session.config["variablePresentation"] = {"all": "hide", "protected": "inline"}
        with run(session, target(code_to_debug)):
            session.set_breakpoints(code_to_debug, all)

        stop = session.wait_for_stop()
        scopes = session.request("scopes", {"frameId": stop.frame_id})["scopes"]
        globals_ref = scopes[0]["variablesReference"]
        vars = session.request("variables", {"variablesReference": globals_ref})[
            "variables"
        ]

        # Variables must be sorted by name.
        a, b, c = (v for v in vars if v["name"] in ("a", "b", "c"))
        assert (a["name"], b["name"], c["name"]) == ("a", "b", "c")

        # Fetch children variables of the dict.
        b_vars = session.request(
            "variables", {"variablesReference": b["variablesReference"]}
        )["variables"]
        assert b_vars == [
            some.dict.containing(
                {
                    "type": "int",
                    "value": "1",
                    "name": "'one'",
                    "evaluateName": "b['one']",
                    "variablesReference": 0,
                }
            ),
            some.dict.containing(
                {
                    "type": "str",
                    "value": "'two'",
                    "name": "2",
                    "evaluateName": "b[2]",
                    "variablesReference": 0,
                }
            ),
            some.dict.containing(
                {
                    "type": "int",
                    "value": "2",
                    "name": "len()",
                    "evaluateName": "len(b)",
                    "variablesReference": 0,
                    "presentationHint": {"attributes": ["readOnly"]},
                }
            ),
        ]

        session.request_continue()


def test_variable_sort(pyfile, target, run):
    @pyfile
    def code_to_debug():
        import debuggee

        debuggee.setup()
        b_test = {"spam": "A", "eggs": "B", "abcd": "C"}  # noqa
        _b_test = 12  # noqa
        __b_test = 13  # noqa
        __b_test__ = 14  # noqa
        a_test = 1  # noqa
        _a_test = 2  # noqa
        __a_test = 3  # noqa
        __a_test__ = 4  # noqa
        c_test = {1: "one", 2: "two", 10: "ten"}  # noqa
        _c_test = 22  # noqa
        __c_test = 23  # noqa
        __c_test__ = 24  # noqa
        d = 3  # noqa
        print("done")  # @bp

    with debug.Session() as session:
        session.config["variablePresentation"] = {
            "special": "group",
            "protected": "inline",
        }
        with run(session, target(code_to_debug)):
            session.set_breakpoints(code_to_debug, all)

        stop = session.wait_for_stop()
        scopes = session.request("scopes", {"frameId": stop.frame_id})["scopes"]
        globals_ref = scopes[0]["variablesReference"]
        vars = session.request("variables", {"variablesReference": globals_ref})[
            "variables"
        ]

        var_names = [v["name"] for v in vars if "_test" in v["name"]]
        assert var_names == [
            "a_test",
            "b_test",
            "c_test",
            "_a_test",
            "_b_test",
            "_c_test",
            "__a_test",
            "__b_test",
            "__c_test",
        ]

        (special_vars_entry,) = (v for v in vars if v["name"] == "special variables")
        special_vars_variables = session.request(
            "variables",
            {"variablesReference": special_vars_entry["variablesReference"]},
        )["variables"]
        special_vars_variables = [
            v["name"] for v in special_vars_variables if "_test" in v["name"]
        ]
        assert special_vars_variables == ["__a_test__", "__b_test__", "__c_test__"]

        # String dict keys must be sorted as strings.
        (b_test,) = (v for v in vars if v["name"] == "b_test")
        b_test_vars = session.request(
            "variables", {"variablesReference": b_test["variablesReference"]}
        )["variables"]
        var_names = [v["name"] for v in b_test_vars]
        # Note that the special len() we manually create is not added to special variables.
        expected = [
            "special variables",
            "function variables",
            "'spam'",
            "'eggs'",
            "'abcd'",
            "len()",
        ]
        assert var_names == expected

        # Numeric dict keys must be sorted as numbers.
        if not "https://github.com/microsoft/ptvsd/issues/213":
            (c_test,) = (v for v in vars if v["name"] == "c_test")
            c_test_vars = session.request(
                "variables", {"variablesReference": c_test["variablesReference"]}
            )["variables"]
            var_names = [v["name"] for v in c_test_vars]
            # Note that the special len() we manually create is not added to special variables.
            expected = ["1", "2", "10", "len()"]

            assert var_names == expected

        session.request_continue()


@pytest.mark.parametrize("ret_vis", ("show", "hide", "default"))
def test_return_values(pyfile, target, run, ret_vis):
    @pyfile
    def code_to_debug():
        import debuggee

        debuggee.setup()

        class MyClass(object):
            def do_something(self):
                return "did something"

        def my_func():
            return "did more things"

        MyClass().do_something()  # @bp
        my_func()
        print("done")

    expected1 = some.dict.containing(
        {
            "name": "(return) MyClass.do_something",
            "value": "'did something'",
            "type": "str",
            "presentationHint": some.dict.containing(
                {"attributes": some.list.containing("readOnly")}
            ),
        }
    )

    expected2 = some.dict.containing(
        {
            "name": "(return) my_func",
            "value": "'did more things'",
            "type": "str",
            "presentationHint": some.dict.containing(
                {"attributes": some.list.containing("readOnly")}
            ),
        }
    )

    with debug.Session() as session:
        if ret_vis != "default":
            session.config["showReturnValue"] = ret_vis != "hide"

        with run(session, target(code_to_debug)):
            session.set_breakpoints(code_to_debug, all)

        stop = session.wait_for_stop()
        session.request("next", {"threadId": stop.thread_id})
        stop = session.wait_for_stop("step")
        scopes = session.request("scopes", {"frameId": stop.frame_id})["scopes"]
        globals_ref = scopes[0]["variablesReference"]

        vars = session.request("variables", {"variablesReference": globals_ref})[
            "variables"
        ]
        ret_vars = [v for v in vars if v["name"].startswith("(return)")]
        assert ret_vars == ([expected1] if ret_vis != "hide" else [])

        session.request("next", {"threadId": stop.thread_id})
        stop = session.wait_for_stop("step")

        # Variable reference for the scope is not invalidated after the step.
        vars = session.request("variables", {"variablesReference": globals_ref})[
            "variables"
        ]
        ret_vars = [v for v in vars if v["name"].startswith("(return)")]
        assert ret_vars == ([expected1, expected2] if ret_vis != "hide" else [])

        session.request_continue()


# On Python 3, variable names can contain Unicode characters.
def test_unicode(pyfile, target, run):
    @pyfile
    def code_to_debug():
        import debuggee
        import debugpy

        globals()["\u16A0"] = 123
        debuggee.setup()
        debugpy.breakpoint()
        print("break")

    with debug.Session() as session:
        with run(session, target(code_to_debug)):
            pass

        stop = session.wait_for_stop()
        eval = session.request(
            "evaluate", {"expression": "\u16A0", "frameId": stop.frame_id}
        )
        assert eval == some.dict.containing({"type": "int", "result": "123"})
        session.request_continue()


# Numbers should be properly hex-formatted in all positions: variable values, list
# indices, dict keys etc.
def test_hex_numbers(pyfile, target, run):
    @pyfile
    def code_to_debug():
        import debuggee

        debuggee.setup()
        a = 100
        b = [1, 10, 100]
        c = {10: 10, 100: 100, 1000: 1000}
        d = {(1, 10, 100): (10000, 100000, 100000)}
        print((a, b, c, d))  # @bp

    with debug.Session() as session:
        session.config["variablePresentation"] = {"all": "hide", "protected": "inline"}

        with run(session, target(code_to_debug)):
            session.set_breakpoints(code_to_debug, all)

        stop = session.wait_for_stop()
        scopes = session.request("scopes", {"frameId": stop.frame_id})["scopes"]
        globals_ref = scopes[0]["variablesReference"]

        vars = session.request(
            "variables", {"variablesReference": globals_ref, "format": {"hex": True}}
        )["variables"]
        a, b, c, d = (v for v in vars if v["name"] in ("a", "b", "c", "d"))
        assert a == some.dict.containing(
            {
                "name": "a",
                "value": "0x64",
                "type": "int",
                "evaluateName": "a",
                "variablesReference": 0,
            }
        )
        assert b == some.dict.containing(
            {
                "name": "b",
                "value": "[0x1, 0xa, 0x64]",
                "type": "list",
                "evaluateName": "b",
                "variablesReference": some.dap.id,
            }
        )
        assert c == some.dict.containing(
            {
                "name": "c",
                "value": "{0xa: 0xa, 0x64: 0x64, 0x3e8: 0x3e8}",
                "type": "dict",
                "evaluateName": "c",
                "variablesReference": some.dap.id,
            }
        )
        assert d == some.dict.containing(
            {
                "name": "d",
                "value": "{(0x1, 0xa, 0x64): (0x2710, 0x186a0, 0x186a0)}",
                "type": "dict",
                "evaluateName": "d",
                "variablesReference": some.dap.id,
            }
        )

        b_vars = session.request(
            "variables",
            {"variablesReference": b["variablesReference"], "format": {"hex": True}},
        )["variables"]
        assert b_vars == [
            some.dict.containing(
                {
                    "name": "0x0",
                    "value": "0x1",
                    "type": "int",
                    "evaluateName": "b[0]",
                    "variablesReference": 0,
                }
            ),
            some.dict.containing(
                {
                    "name": "0x1",
                    "value": "0xa",
                    "type": "int",
                    "evaluateName": "b[1]",
                    "variablesReference": 0,
                }
            ),
            some.dict.containing(
                {
                    "name": "0x2",
                    "value": "0x64",
                    "type": "int",
                    "evaluateName": "b[2]",
                    "variablesReference": 0,
                }
            ),
            some.dict.containing(
                {
                    "name": "len()",
                    "value": "0x3",
                    "type": "int",
                    "evaluateName": "len(b)",
                    "variablesReference": 0,
                    "presentationHint": {"attributes": ["readOnly"]},
                }
            ),
        ]

        c_vars = session.request(
            "variables",
            {"variablesReference": c["variablesReference"], "format": {"hex": True}},
        )["variables"]
        # Use dict sequence on Python 3.6 onwards.
        assert c_vars == [
            some.dict.containing(
                {
                    "name": "0xa",
                    "value": "0xa",
                    "type": "int",
                    "evaluateName": "c[10]",
                    "variablesReference": 0,
                }
            ),
            some.dict.containing(
                {
                    "name": "0x64",
                    "value": "0x64",
                    "type": "int",
                    "evaluateName": "c[100]",
                    "variablesReference": 0,
                }
            ),
            some.dict.containing(
                {
                    "name": "0x3e8",
                    "value": "0x3e8",
                    "type": "int",
                    "evaluateName": "c[1000]",
                    "variablesReference": 0,
                }
            ),
            some.dict.containing(
                {
                    "name": "len()",
                    "value": "0x3",
                    "type": "int",
                    "evaluateName": "len(c)",
                    "variablesReference": 0,
                    "presentationHint": {"attributes": ["readOnly"]},
                }
            ),
        ]

        d_vars = session.request(
            "variables",
            {"variablesReference": d["variablesReference"], "format": {"hex": True}},
        )["variables"]
        assert d_vars == [
            some.dict.containing(
                {
                    "name": "(0x1, 0xa, 0x64)",
                    "value": "(0x2710, 0x186a0, 0x186a0)",
                    "type": "tuple",
                    "evaluateName": "d[(1, 10, 100)]",
                    "variablesReference": some.dap.id,
                }
            ),
            some.dict.containing(
                {
                    "name": "len()",
                    "value": "0x1",
                    "type": "int",
                    "evaluateName": "len(d)",
                    "variablesReference": 0,
                    "presentationHint": {"attributes": ["readOnly"]},
                }
            ),
        ]

        d_item0 = d_vars[0]
        d_item0_vars = session.request(
            "variables",
            {
                "variablesReference": d_item0["variablesReference"],
                "format": {"hex": True},
            },
        )["variables"]
        assert d_item0_vars == [
            some.dict.containing(
                {
                    "name": "0x0",
                    "value": "0x2710",
                    "type": "int",
                    "evaluateName": "d[(1, 10, 100)][0]",
                    "variablesReference": 0,
                }
            ),
            some.dict.containing(
                {
                    "name": "0x1",
                    "value": "0x186a0",
                    "type": "int",
                    "evaluateName": "d[(1, 10, 100)][1]",
                    "variablesReference": 0,
                }
            ),
            some.dict.containing(
                {
                    "name": "0x2",
                    "value": "0x186a0",
                    "type": "int",
                    "evaluateName": "d[(1, 10, 100)][2]",
                    "variablesReference": 0,
                }
            ),
            some.dict.containing(
                {
                    "name": "len()",
                    "value": "0x3",
                    "type": "int",
                    "evaluateName": "len(d[(1, 10, 100)])",
                    "variablesReference": 0,
                    "presentationHint": {"attributes": ["readOnly"]},
                }
            ),
        ]

        session.request_continue()


def test_set_variable(pyfile, target, run):
    @pyfile
    def code_to_debug():
        import debuggee
        import debugpy
        from debuggee import backchannel

        debuggee.setup()
        a = 1
        debugpy.breakpoint()
        backchannel.send(a)

    with debug.Session() as session:
        backchannel = session.open_backchannel()
        with run(session, target(code_to_debug)):
            pass

        stop = session.wait_for_stop()
        scopes = session.request("scopes", {"frameId": stop.frame_id})["scopes"]
        globals_ref = scopes[0]["variablesReference"]
        vars = session.request("variables", {"variablesReference": globals_ref})[
            "variables"
        ]

        (a,) = (v for v in vars if v["name"] == "a")
        assert a == some.dict.containing(
            {
                "type": "int",
                "value": "1",
                "name": "a",
                "evaluateName": "a",
                "variablesReference": 0,
            }
        )

        set_a = session.request(
            "setVariable",
            {"variablesReference": globals_ref, "name": "a", "value": "1000"},
        )
        assert set_a == some.dict.containing({"type": "int", "value": "1000"})

        session.request_continue()
        assert backchannel.receive() == 1000


def test_set_expression(pyfile, target, run):
    @pyfile
    def code_to_debug():
        import debuggee
        from debuggee import backchannel

        debuggee.setup()
        a = 1
        backchannel.send(a)  # @bp

    with debug.Session() as session:
        backchannel = session.open_backchannel()
        with run(session, target(code_to_debug)):
            session.set_breakpoints(code_to_debug, all)

        stop = session.wait_for_stop()
        scopes = session.request("scopes", {"frameId": stop.frame_id})["scopes"]
        globals_ref = scopes[0]["variablesReference"]

        vars = session.request("variables", {"variablesReference": globals_ref})[
            "variables"
        ]
        (a,) = (v for v in vars if v["name"] == "a")
        assert a == some.dict.containing(
            {
                "type": "int",
                "value": "1",
                "name": "a",
                "evaluateName": "a",
                "variablesReference": 0,
            }
        )

        set_a = session.request(
            "setExpression",
            {"frameId": stop.frame_id, "expression": "a", "value": "1000"},
        )
        assert set_a == some.dict.containing({"type": "int", "value": "1000"})

        session.request_continue()
        assert backchannel.receive() == 1000


def test_evaluate_thread_locks(pyfile, target, run):
    @pyfile
    def code_to_debug():
        """
        The idea here is that a secondary thread does the processing of instructions,
        so, when all threads are stopped, doing an evaluation for:

        processor.process('xxx')

        would be locked until secondary threads start running.
        See: https://github.com/microsoft/debugpy/issues/157
        """

        import debuggee
        import queue
        import threading

        debuggee.setup()

        class EchoThread(threading.Thread):
            def __init__(self, queue):
                threading.Thread.__init__(self)
                self._queue = queue

            def run(self):
                while True:
                    obj = self._queue.get()
                    if obj == "finish":
                        break

                    print("processed", obj.value)
                    obj.event.set()

        class NotificationObject(object):
            def __init__(self, value):
                self.value = value
                self.event = threading.Event()

        class Processor(object):
            def __init__(self, queue):
                self._queue = queue

            def process(self, i):
                obj = NotificationObject(i)
                self._queue.put(obj)
                assert obj.event.wait()

            def finish(self):
                self._queue.put("finish")

        if __name__ == "__main__":
            q = queue.Queue()
            echo_thread = EchoThread(q)
            processor = Processor(q)
            echo_thread.start()

            processor.process(1)
            processor.process(2)  # @bp
            processor.process(3)
            processor.finish()

    with debug.Session() as session:

        # During the evaluation we'll actually have continued/stopped events because
        # we're letting threads run at that time. Let's ignore these in the test.
        session.ignore_unobserved.extend([timeline.Event("stopped")])

        session.config.env.update({"PYDEVD_UNBLOCK_THREADS_TIMEOUT": "0.5"})

        with run(session, target(code_to_debug)):
            session.set_breakpoints(code_to_debug, all)

        stop = session.wait_for_stop()

        evaluate = session.request(
            "evaluate",
            {"expression": "processor.process('foo')", "frameId": stop.frame_id},
        )
        assert evaluate == some.dict.containing({"result": "None"})

        session.request_continue()
