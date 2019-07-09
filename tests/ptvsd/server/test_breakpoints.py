# -*- coding: utf-8 -*-
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import platform
import pytest
import re
import sys

from ptvsd.common import fmt
from tests import code, debug, test_data
from tests.patterns import some


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
    test_py = BP_TEST_ROOT / "ನನ್ನ_ಸ್ಕ್ರಿಪ್ಟ್.py"
    lines = code.get_marked_line_numbers(test_py)

    with debug.Session() as session:
        session.initialize(target=(run_as, test_py), start_method=start_method)
        session.set_breakpoints(test_py, [lines["bp"]])
        session.start_debugging()

        session.wait_for_stop("breakpoint", expected_frames=[
            some.dict.containing({
                "source": some.source(test_py),
                "name": "ಏನಾದರೂ_ಮಾಡು",
            }),
        ])

        session.request_continue()
        session.wait_for_exit()


@pytest.mark.parametrize(
    "condition_kind",
    [
        ("condition",),
        ("hitCondition",),
        ("hitCondition", "eq"),
        ("hitCondition", "gt"),
        ("hitCondition", "ge"),
        ("hitCondition", "lt"),
        ("hitCondition", "le"),
        ("hitCondition", "mod"),
    ],
)
def test_conditional_breakpoint(pyfile, start_method, run_as, condition_kind):
    @pyfile
    def code_to_debug():
        import debug_me  # noqa

        for i in range(0, 10):
            print(i)  # @bp

    condition_property = condition_kind[0]
    condition, value, hits = {
        ("condition",): ("i==5", "5", 1),
        ("hitCondition",): ("5", "4", 1),
        ("hitCondition", "eq"): ("==5", "4", 1),
        ("hitCondition", "gt"): (">5", "5", 5),
        ("hitCondition", "ge"): (">=5", "4", 6),
        ("hitCondition", "lt"): ("<5", "0", 4),
        ("hitCondition", "le"): ("<=5", "0", 5),
        ("hitCondition", "mod"): ("%3", "2", 3),
    }[condition_kind]

    lines = code_to_debug.lines
    with debug.Session() as session:
        session.initialize(target=(run_as, code_to_debug), start_method=start_method)
        session.request(
            "setBreakpoints",
            arguments={
                "source": {"path": code_to_debug},
                "breakpoints": [{"line": lines["bp"], condition_property: condition}],
            },
        )
        session.start_debugging()

        frame_id = session.wait_for_stop(expected_frames=[
            some.dict.containing({"line": lines["bp"]})
        ]).frame_id

        scopes = session.request(
            "scopes", arguments={"frameId": frame_id}
        )["scopes"]

        assert len(scopes) > 0

        variables = session.request(
            "variables",
            arguments={"variablesReference": scopes[0]["variablesReference"]},
        )["variables"]

        variables = [v for v in variables if v["name"] == "i"]
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

        session.wait_for_stop(expected_frames=[
            some.dict.containing({
                "source": some.source(script2),
                "line": script2.lines["bp"],
            })
        ])

        session.request_continue()

        session.wait_for_stop(expected_frames=[
            some.dict.containing({
                "source": some.source(script1),
                "line": script1.lines["bp"],
            })
        ])

        session.request_continue()
        session.wait_for_exit()


@pytest.mark.parametrize("error_name", ["NameError", ""])
def test_error_in_condition(pyfile, start_method, run_as, error_name):
    @pyfile
    def code_to_debug():
        import debug_me  # noqa

        for i in range(1, 10):  # @bp
            pass

    error_name = error_name or "ZeroDivisionError"

    # NOTE: NameError in condition, is a special case. Pydevd is configured to skip
    # traceback for name errors. See https://github.com/Microsoft/ptvsd/issues/853
    # for more details. For all other errors we should be printing traceback.
    condition, expect_traceback = {
        "NameError": ("no_such_name", False),
        "ZeroDivisionError": ("1 / 0", True),
    }[error_name]

    with debug.Session() as session:
        session.initialize(target=(run_as, code_to_debug), start_method=start_method)
        session.send_request(
            "setBreakpoints",
            arguments={
                "source": {"path": code_to_debug},
                "breakpoints": [
                    {"line": code_to_debug.lines["bp"], "condition": condition}
                ],
            },
        ).wait_for_response()
        session.start_debugging()
        session.wait_for_exit()

        assert not session.captured_stdout()

        error_name = error_name.encode("ascii")
        if expect_traceback:
            assert error_name in session.captured_stderr()
        else:
            assert error_name not in session.captured_stderr()


@pytest.mark.parametrize("condition", ["condition", ""])
def test_log_point(pyfile, start_method, run_as, condition):
    @pyfile
    def code_to_debug():
        import debug_me  # noqa

        for i in range(0, 10):
            print(i * 10)  # @bp

    lines = code_to_debug.lines
    with debug.Session() as session:
        session.initialize(target=(run_as, code_to_debug), start_method=start_method)

        bp = {"line": lines["bp"], "logMessage": "{i}"}
        if condition:
            bp["condition"] = "i == 5"

        session.request(
            "setBreakpoints",
            arguments={
                "source": {"path": code_to_debug},
                "breakpoints": [bp],
            },
        )
        session.start_debugging()

        if condition:
            frame_id = session.wait_for_stop(expected_frames=[
                some.dict.containing({
                    "line": lines["bp"]
                })
            ]).frame_id

            scopes = session.request(
                "scopes", arguments={"frameId": frame_id}
            )["scopes"]

            assert len(scopes) > 0

            variables = session.request(
                "variables",
                arguments={"variablesReference": scopes[0]["variablesReference"]},
            )["variables"]
            variables = [v for v in variables if v["name"] == "i"]

            assert variables == [
                some.dict.containing(
                    {"name": "i", "type": "int", "value": "5", "evaluateName": "i"}
                )
            ]

            session.request_continue()

        session.wait_for_exit()

        assert not session.captured_stderr()

        expected_stdout = "".join((
            fmt(r"{0}\r?\n{1}\r?\n", re.escape(str(i)), re.escape(str(i * 10)))
            for i in range(0, 10)
        ))
        assert session.output("stdout") == some.str.matching(expected_stdout)


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
        import debug_me  # noqa

        for i in range(0, 10):
            print(i)  # @bp

    lines = code_to_debug.lines
    with debug.Session() as session:
        session.initialize(
            target=(run_as, code_to_debug),
            start_method=start_method,
        )
        session.set_breakpoints(code_to_debug, [lines["bp"]])
        session.start_debugging()

        hit = session.wait_for_stop()
        assert lines["bp"] == hit.frames[0]["line"]

        # remove breakpoints in file
        session.set_breakpoints(code_to_debug, [])
        session.request_continue()
        session.wait_for_exit()

        expected_stdout = "".join((fmt("{0}\n", i) for i in range(0, 10)))
        assert session.output("stdout") == expected_stdout


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

    lines = code_to_debug.lines
    with debug.Session() as session:
        session.initialize(target=(run_as, code_to_debug), start_method=start_method)

        requested_bps = [
            lines["bp1-requested"],
            lines["bp2-requested"],
            lines["bp3-requested"],
        ]
        if sys.version_info < (3,):
            requested_bps += [
                lines["bp4-requested-1"],
                lines["bp4-requested-2"],
            ]

        actual_bps = session.set_breakpoints(code_to_debug, requested_bps)
        actual_bps = [bp["line"] for bp in actual_bps]

        expected_bps = [
            lines["bp1-expected"],
            lines["bp2-expected"],
            lines["bp3-expected"],
        ]
        if sys.version_info < (3,):
            expected_bps += [lines["bp4-expected"], lines["bp4-expected"]]

        assert expected_bps == actual_bps

        # Now let's make sure that we hit all of the expected breakpoints,
        # and stop where we expect them to be.

        session.start_debugging()

        # If there's multiple breakpoints on the same line, we only stop once,
        # so remove duplicates first.
        expected_bps = sorted(set(expected_bps))

        while expected_bps:
            expected_line = expected_bps.pop(0)
            session.wait_for_stop(expected_frames=[
                some.dict.containing({"line": expected_line})
            ])
            session.request_continue()

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

        stop = session.wait_for_stop()
        assert len(stop.frames) > 100

        # Now try to retrieve the same stack in chunks, and check that it matches.
        frames = []
        for _ in range(5):
            stack_trace = session.request(
                "stackTrace",
                arguments={
                    "threadId": stop.thread_id,
                    "startFrame": len(frames),
                    "levels": 25,
                },
            )

            assert stack_trace["totalFrames"] > 0
            frames += stack_trace["stackFrames"]

        assert stop.frames == frames

        session.request_continue()
        session.wait_for_exit()
