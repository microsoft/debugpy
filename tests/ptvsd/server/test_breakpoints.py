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
from tests import debug, test_data
from tests.patterns import some


bp_root = test_data / "bp"


def test_path_with_ampersand(start_method, run_as):
    test_py = bp_root / "a&b" / "test.py"

    with debug.Session(start_method) as session:
        session.initialize(target=(run_as, test_py))
        session.set_breakpoints(test_py, ["two"])
        session.start_debugging()

        session.wait_for_stop(
            "breakpoint",
            expected_frames=[
                some.dap.frame(test_py, line="two"),
            ],
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
    test_py = bp_root / "ನನ್ನ_ಸ್ಕ್ರಿಪ್ಟ್.py"

    with debug.Session(start_method) as session:
        session.initialize(target=(run_as, test_py))
        session.set_breakpoints(test_py, ["bp"])
        session.start_debugging()

        session.wait_for_stop(
            "breakpoint",
            expected_frames=[some.dap.frame(test_py, name="ಏನಾದರೂ_ಮಾಡು", line="bp")],
        )

        session.request_continue()
        session.wait_for_exit()


@pytest.mark.parametrize(
    "condition_kind",
    [
        "condition",
        "hitCondition",
        "hitCondition-eq",
        "hitCondition-gt",
        "hitCondition-ge",
        "hitCondition-lt",
        "hitCondition-le",
        "hitCondition-mod",
    ],
)
def test_conditional_breakpoint(pyfile, start_method, run_as, condition_kind):
    @pyfile
    def code_to_debug():
        import debug_me  # noqa

        for i in range(0, 10):
            print(i)  # @bp

    condition_property = condition_kind.partition("-")[0]
    condition, value, hits = {
        "condition": ("i==5", "5", 1),
        "hitCondition": ("5", "4", 1),
        "hitCondition-eq": ("==5", "4", 1),
        "hitCondition-gt": (">5", "5", 5),
        "hitCondition-ge": (">=5", "4", 6),
        "hitCondition-lt": ("<5", "0", 4),
        "hitCondition-le": ("<=5", "0", 5),
        "hitCondition-mod": ("%3", "2", 3),
    }[condition_kind]

    with debug.Session(start_method) as session:
        session.initialize(target=(run_as, code_to_debug))
        session.request(
            "setBreakpoints",
            {
                "source": {"path": code_to_debug},
                "breakpoints": [
                    {"line": code_to_debug.lines["bp"], condition_property: condition}
                ],
            },
        )
        session.start_debugging()

        session.wait_for_stop(
            expected_frames=[some.dap.frame(code_to_debug, line="bp")]
        )

        session.get_variables()

        var_i = session.get_variable("i")
        assert var_i == some.dict.containing(
            {"name": "i", "type": "int", "value": value, "evaluateName": "i"}
        )

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

    with debug.Session(start_method) as session:
        session.initialize(target=(run_as, script2))
        session.set_breakpoints(script1, all)
        session.set_breakpoints(script2, all)
        session.start_debugging()

        session.wait_for_stop(expected_frames=[some.dap.frame(script2, line="bp")])

        session.request_continue()

        session.wait_for_stop(expected_frames=[some.dap.frame(script1, line="bp")])

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

    with debug.Session(start_method) as session:
        session.initialize(target=(run_as, code_to_debug))
        session.request(
            "setBreakpoints",
            {
                "source": {"path": code_to_debug},
                "breakpoints": [
                    {"line": code_to_debug.lines["bp"], "condition": condition}
                ],
            },
        )
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
        ()  # @wait_for_output

    lines = code_to_debug.lines
    with debug.Session(start_method) as session:
        session.initialize(target=(run_as, code_to_debug))

        bp = {"line": lines["bp"], "logMessage": "{i}"}
        if condition:
            bp["condition"] = "i == 5"

        session.request(
            "setBreakpoints",
            arguments={
                "source": {"path": code_to_debug},
                "breakpoints": [bp, {"line": lines["wait_for_output"]}],
            },
        )
        session.start_debugging()

        if condition:
            session.wait_for_stop(
                "breakpoint",
                expected_frames=[
                    some.dap.frame(code_to_debug, line="bp")
                ],
            )

            var_i = session.get_variable("i")
            assert var_i == some.dict.containing(
                {"name": "i",  "evaluateName": "i", "type": "int", "value": "5"},
            )

            session.request_continue()

        session.wait_for_stop(
            "breakpoint",
            expected_frames=[
                some.dap.frame(code_to_debug, line="wait_for_output")
            ],
        )
        session.request_continue()
        session.wait_for_exit()

        assert not session.captured_stderr()

        expected_stdout = "".join(
            (
                fmt(r"{0}\r?\n{1}\r?\n", re.escape(str(i)), re.escape(str(i * 10)))
                for i in range(0, 10)
            )
        )
        assert session.output("stdout") == some.str.matching(expected_stdout)


def test_package_launch():
    cwd = test_data / "testpkgs"
    test_py = cwd / "pkg1" / "__main__.py"

    with debug.Session("launch") as session:
        session.initialize(target=("module", "pkg1"), cwd=cwd)
        session.set_breakpoints(test_py, ["two"])
        session.start_debugging()

        session.wait_for_stop(
            "breakpoint",
            expected_frames=[
                some.dap.frame(test_py, line="two"),
            ],
        )

        session.request_continue()
        session.wait_for_exit()


def test_add_and_remove_breakpoint(pyfile, start_method, run_as):
    @pyfile
    def code_to_debug():
        import debug_me  # noqa

        for i in range(0, 10):
            print(i)  # @bp
        ()  # @wait_for_output

    with debug.Session(start_method) as session:
        session.initialize(target=(run_as, code_to_debug))
        session.set_breakpoints(code_to_debug, all)
        session.start_debugging()

        session.wait_for_stop(
            "breakpoint",
            expected_frames=[
                some.dap.frame(code_to_debug, line="bp"),
            ],
        )

        # Remove breakpoint inside the loop.
        session.set_breakpoints(code_to_debug, ["wait_for_output"])
        session.request_continue()

        session.wait_for_stop(
            "breakpoint",
            expected_frames=[
                some.dap.frame(code_to_debug, line="wait_for_output")
            ],
        )
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

    with debug.Session(start_method) as session:
        session.initialize(target=(run_as, code_to_debug))

        bp_markers = ["bp1-requested", "bp2-requested", "bp3-requested"]
        if sys.version_info < (3,):
            bp_markers += ["bp4-requested-1", "bp4-requested-2"]

        bps = session.set_breakpoints(code_to_debug, bp_markers)
        actual_lines = [bp["line"] for bp in bps]

        expected_markers = ["bp1-expected", "bp2-expected", "bp3-expected"]
        if sys.version_info < (3,):
            expected_markers += ["bp4-expected", "bp4-expected"]
        expected_lines = [code_to_debug.lines[marker] for marker in expected_markers]

        assert actual_lines == expected_lines

        # Now let's make sure that we hit all of the expected breakpoints,
        # and stop where we expect them to be.
        session.start_debugging()

        # If there's multiple breakpoints on the same line, we only stop once,
        # so remove duplicates first.
        expected_lines = sorted(set(expected_lines))

        while expected_lines:
            expected_line = expected_lines.pop(0)
            session.wait_for_stop(
                "breakpoint",
                expected_frames=[some.dap.frame(code_to_debug, line=expected_line)],
            )
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

    with debug.Session(start_method) as session:
        session.initialize(target=(run_as, code_to_debug))
        session.set_breakpoints(code_to_debug, all)
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
