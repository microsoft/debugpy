# -*- coding: utf-8 -*-
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import os.path
import platform
import pytest
import re
import sys

from tests import code, debug, test_data
from tests.patterns import some
from tests.timeline import Event


BP_TEST_ROOT = test_data / "bp"


def test_path_with_ampersand(start_method, run_as):
    test_py = BP_TEST_ROOT / "a&b" / "test.py"
    lines = code.get_marked_line_numbers(test_py)

    with debug.Session(start_method) as session:
        session.initialize(target=(run_as, test_py))
        session.set_breakpoints(test_py, [lines["two"]])
        session.start_debugging()

        session.wait_for_stop(
            "breakpoint",
            expected_frames=[some.dict.containing({"source": some.source(test_py)})],
        )

        session.request_continue()
        session.wait_for_exit()


@pytest.mark.skipif(
    sys.version_info < (3, 0), reason="Paths are not Unicode in Python 2.7"
)
@pytest.mark.skipif(
    platform.system() == "Windows" and sys.version_info < (3, 6),
    reason="https://github.com/Microsoft/ptvsd/issues/1124#issuecomment-459506802",
)
def test_path_with_unicode(start_method, run_as):
    test_py = os.path.join(BP_TEST_ROOT, "ನನ್ನ_ಸ್ಕ್ರಿಪ್ಟ್.py")
    lines = code.get_marked_line_numbers(test_py)

    with debug.Session() as session:
        session.initialize(target=(run_as, test_py), start_method=start_method)
        session.set_breakpoints(test_py, [lines["bp"]])
        session.start_debugging()
        hit = session.wait_for_stop("breakpoint")
        assert hit.frames[0]["source"]["path"] == some.path(test_py)
        assert "ಏನಾದರೂ_ಮಾಡು" == hit.frames[0]["name"]

        session.request_continue()
        session.wait_for_exit()


@pytest.mark.parametrize(
    "condition_key",
    [
        "condition_var",
        "hitCondition_#",
        "hitCondition_eq",
        "hitCondition_gt",
        "hitCondition_ge",
        "hitCondition_lt",
        "hitCondition_le",
        "hitCondition_mod",
    ],
)
def test_conditional_breakpoint(pyfile, start_method, run_as, condition_key):
    @pyfile
    def code_to_debug():
        import debug_me  # noqa

        for i in range(0, 10):
            print(i)  # @bp

    expected = {
        "condition_var": ("condition", "i==5", "5", 1),
        "hitCondition_#": ("hitCondition", "5", "4", 1),
        "hitCondition_eq": ("hitCondition", "==5", "4", 1),
        "hitCondition_gt": ("hitCondition", ">5", "5", 5),
        "hitCondition_ge": ("hitCondition", ">=5", "4", 6),
        "hitCondition_lt": ("hitCondition", "<5", "0", 4),
        "hitCondition_le": ("hitCondition", "<=5", "0", 5),
        "hitCondition_mod": ("hitCondition", "%3", "2", 3),
    }
    condition_type, condition, value, hits = expected[condition_key]

    lines = code_to_debug.lines
    with debug.Session() as session:
        session.initialize(target=(run_as, code_to_debug), start_method=start_method)
        session.send_request(
            "setBreakpoints",
            arguments={
                "source": {"path": code_to_debug},
                "breakpoints": [{"line": lines["bp"], condition_type: condition}],
            },
        ).wait_for_response()
        session.start_debugging()
        hit = session.wait_for_stop()
        assert lines["bp"] == hit.frames[0]["line"]

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
            v for v in resp_variables.body["variables"] if v["name"] == "i"
        )
        assert variables == [
            some.dict.containing(
                {"name": "i", "type": "int", "value": value, "evaluateName": "i"}
            )
        ]

        session.request_continue()
        for i in range(1, hits):
            session.wait_for_stop()
            session.request_continue()
        session.wait_for_exit()


def test_crossfile_breakpoint(pyfile, start_method, run_as):
    @pyfile
    def script1():
        import debug_me  # noqa

        def do_something():
            print("do something")  # @bp

    @pyfile
    def script2():
        import debug_me  # noqa
        import script1

        script1.do_something()  # @bp
        print("Done")

    with debug.Session() as session:
        session.initialize(target=(run_as, script2), start_method=start_method)
        session.set_breakpoints(script1, lines=[script1.lines["bp"]])
        session.set_breakpoints(script2, lines=[script2.lines["bp"]])
        session.start_debugging()

        hit = session.wait_for_stop()
        assert script2.lines["bp"] == hit.frames[0]["line"]
        assert hit.frames[0]["source"]["path"] == some.path(script2)

        session.request_continue()
        hit = session.wait_for_stop()
        assert script1.lines["bp"] == hit.frames[0]["line"]
        assert hit.frames[0]["source"]["path"] == some.path(script1)

        session.request_continue()
        session.wait_for_exit()


@pytest.mark.parametrize("error_name", ["NameError", "OtherError"])
def test_error_in_condition(pyfile, start_method, run_as, error_name):
    @pyfile
    def code_to_debug():
        import debug_me  # noqa

        def do_something_bad():
            raise ArithmeticError()

        for i in range(1, 10):  # @bp
            pass

    # NOTE: NameError in condition, is a special case. Pydevd is configured to skip
    # traceback for name errors. See https://github.com/Microsoft/ptvsd/issues/853
    # for more details. For all other errors we should be printing traceback.
    condition = {
        "NameError": ("x==5"),  # 'x' does not exist in the debuggee
        "OtherError": ("do_something_bad()==5"),  # throws some error
    }

    lines = code_to_debug.lines
    with debug.Session() as session:
        session.initialize(target=(run_as, code_to_debug), start_method=start_method)
        session.send_request(
            "setBreakpoints",
            arguments={
                "source": {"path": code_to_debug},
                "breakpoints": [
                    {"line": lines["bp"], "condition": condition[error_name]}
                ],
            },
        ).wait_for_response()
        session.start_debugging()

        session.wait_for_exit()
        assert session.get_stdout_as_string() == b""
        if error_name == "NameError":
            assert session.get_stderr_as_string().find(b"NameError") == -1
        else:
            assert session.get_stderr_as_string().find(b"ArithmeticError") > 0


def test_log_point(pyfile, start_method, run_as):
    @pyfile
    def code_to_debug():
        import debug_me  # noqa

        a = 10
        for i in range(1, a):
            print("value: %d" % i)  # @bp
        # Break at end too so that we're sure we get all output
        # events before the break.
        a = 10  # @end

    lines = code_to_debug.lines
    with debug.Session() as session:
        session.initialize(target=(run_as, code_to_debug), start_method=start_method)
        session.send_request(
            "setBreakpoints",
            arguments={
                "source": {"path": code_to_debug},
                "breakpoints": [
                    {"line": lines["bp"], "logMessage": "log: {a + i}"},
                    {"line": lines["end"]},
                ],
            },
        ).wait_for_response()
        session.start_debugging()

        # Breakpoint at the end just to make sure we get all output events.
        hit = session.wait_for_stop()
        assert lines["end"] == hit.frames[0]["line"]

        session.request_continue()

        session.wait_for_exit()
        assert session.get_stderr_as_string() == b""

        output = session.all_occurrences_of(
            Event("output", some.dict.containing({"category": "stdout"}))
        )
        output_str = "".join(o.body["output"] for o in output)
        logged = sorted(int(i) for i in re.findall(r"log:\s([0-9]*)", output_str))
        values = sorted(int(i) for i in re.findall(r"value:\s([0-9]*)", output_str))

        assert logged == list(range(11, 20))
        assert values == list(range(1, 10))


def test_condition_with_log_point(pyfile, start_method, run_as):
    @pyfile
    def code_to_debug():
        import debug_me  # noqa

        a = 10
        for i in range(1, a):
            print("value: %d" % i)  # @bp
        # Break at end too so that we're sure we get all output
        # events before the break.
        a = 10  # @end

    lines = code_to_debug.lines
    with debug.Session() as session:
        session.initialize(target=(run_as, code_to_debug), start_method=start_method)
        session.send_request(
            "setBreakpoints",
            arguments={
                "source": {"path": code_to_debug},
                "breakpoints": [
                    {
                        "line": lines["bp"],
                        "logMessage": "log: {a + i}",
                        "condition": "i==5",
                    },
                    {"line": lines["end"]},
                ],
            },
        ).wait_for_response()
        session.start_debugging()
        hit = session.wait_for_stop()
        assert lines["end"] == hit.frames[0]["line"]

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
            v for v in resp_variables.body["variables"] if v["name"] == "i"
        )
        assert variables == [
            some.dict.containing(
                {"name": "i", "type": "int", "value": "5", "evaluateName": "i"}
            )
        ]

        session.request_continue()

        # Breakpoint at the end just to make sure we get all output events.
        hit = session.wait_for_stop()
        assert lines["end"] == hit.frames[0]["line"]
        session.request_continue()

        session.wait_for_exit()
        assert session.get_stderr_as_string() == b""

        output = session.all_occurrences_of(
            Event("output", some.dict.containing({"category": "stdout"}))
        )
        output_str = "".join(o.body["output"] for o in output)
        logged = sorted(int(i) for i in re.findall(r"log:\s([0-9]*)", output_str))
        values = sorted(int(i) for i in re.findall(r"value:\s([0-9]*)", output_str))

        assert logged == list(range(11, 20))
        assert values == list(range(1, 10))


def test_package_launch():
    cwd = test_data / "testpkgs"
    test_py = cwd / "pkg1" / "__main__.py"
    lines = code.get_marked_line_numbers(test_py)

    with debug.Session() as session:
        session.initialize(target=("module", "pkg1"), start_method="launch", cwd=cwd)
        session.set_breakpoints(test_py, [lines["two"]])
        session.start_debugging()

        hit = session.wait_for_stop()
        assert lines["two"] == hit.frames[0]["line"]

        session.request_continue()
        session.wait_for_exit()


def test_add_and_remove_breakpoint(pyfile, start_method, run_as):
    @pyfile
    def code_to_debug():
        from debug_me import backchannel

        for i in range(0, 10):
            print(i)  # @bp
        backchannel.receive()

    lines = code_to_debug.lines
    with debug.Session() as session:
        backchannel = session.setup_backchannel()
        session.initialize(
            target=(run_as, code_to_debug),
            start_method=start_method,
            use_backchannel=True,
        )
        session.set_breakpoints(code_to_debug, [lines["bp"]])
        session.start_debugging()

        hit = session.wait_for_stop()
        assert lines["bp"] == hit.frames[0]["line"]

        # remove breakpoints in file
        session.set_breakpoints(code_to_debug, [])
        session.request_continue()

        session.wait_for_next(
            Event("output", some.dict.containing({"category": "stdout", "output": "9"}))
        )
        backchannel.send("done")
        session.wait_for_exit()

        output = session.all_occurrences_of(
            Event("output", some.dict.containing({"category": "stdout"}))
        )
        output = sorted(
            int(o.body["output"].strip())
            for o in output
            if len(o.body["output"].strip()) > 0
        )
        assert list(range(0, 10)) == output


def test_invalid_breakpoints(pyfile, start_method, run_as):
    @pyfile
    def code_to_debug():
        import debug_me  # noqa

        # fmt: off
        b = True
        while b:         # @bp1-expected
            pass         # @bp1-requested
            break

        print()  # @bp2-expected
        [  # @bp2-requested
            1, 2, 3,    # @bp3-expected
        ]               # @bp3-requested

        # Python 2.7 only.
        print()         # @bp4-expected
        print(1,        # @bp4-requested-1
              2, 3,     # @bp4-requested-2
              4, 5, 6)
        # fmt: on

    line_numbers = code_to_debug.lines
    print(line_numbers)

    with debug.Session() as session:
        session.initialize(target=(run_as, code_to_debug), start_method=start_method)

        requested_bps = [
            line_numbers["bp1-requested"],
            line_numbers["bp2-requested"],
            line_numbers["bp3-requested"],
        ]
        if sys.version_info < (3,):
            requested_bps += [
                line_numbers["bp4-requested-1"],
                line_numbers["bp4-requested-2"],
            ]

        actual_bps = session.set_breakpoints(code_to_debug, requested_bps)
        actual_bps = [bp["line"] for bp in actual_bps]

        expected_bps = [
            line_numbers["bp1-expected"],
            line_numbers["bp2-expected"],
            line_numbers["bp3-expected"],
        ]
        if sys.version_info < (3,):
            expected_bps += [line_numbers["bp4-expected"], line_numbers["bp4-expected"]]

        assert expected_bps == actual_bps

        # Now let's make sure that we hit all of the expected breakpoints,
        # and stop where we expect them to be.

        session.start_debugging()

        # If there's multiple breakpoints on the same line, we only stop once,
        # so remove duplicates first.
        expected_bps = sorted(set(expected_bps))

        while expected_bps:
            hit = session.wait_for_stop()
            line = hit.frames[0]["line"]
            assert line == expected_bps[0]
            del expected_bps[0]
            session.send_request("continue").wait_for_response()
        assert not expected_bps

        session.wait_for_exit()


def test_deep_stacks(pyfile, start_method, run_as):
    @pyfile
    def code_to_debug():
        import debug_me  # noqa

        def deep_stack(level):
            if level <= 0:
                print("done")  # @bp
                return level
            deep_stack(level - 1)

        deep_stack(100)

    with debug.Session() as session:
        session.initialize(target=(run_as, code_to_debug), start_method=start_method)

        actual_bps = session.set_breakpoints(code_to_debug, [code_to_debug.lines["bp"]])
        actual_bps = [bp["line"] for bp in actual_bps]
        session.start_debugging()

        hit = session.wait_for_stop()
        full_frames = hit.frames
        assert len(full_frames) > 100

        # Construct stack from parts
        frames = []
        start = 0
        for _ in range(5):
            resp_stacktrace = session.send_request(
                "stackTrace",
                arguments={
                    "threadId": hit.thread_id,
                    "startFrame": start,
                    "levels": 25,
                },
            ).wait_for_response()
            assert resp_stacktrace.body["totalFrames"] > 0
            frames += resp_stacktrace.body["stackFrames"]
            start = len(frames)

        assert full_frames == frames

        session.send_request("continue").wait_for_response()
        session.wait_for_exit()
