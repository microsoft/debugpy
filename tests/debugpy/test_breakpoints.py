# -*- coding: utf-8 -*-
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, division, print_function, unicode_literals

import pytest
import re
import sys

from debugpy.common import fmt
import tests
from tests import debug, test_data
from tests.debug import runners, targets
from tests.patterns import some

bp_root = test_data / "bp"


if not tests.full:

    @pytest.fixture(params=[runners.launch, runners.attach_connect["cli"]])
    def run(request):
        return request.param


@pytest.mark.parametrize("target", targets.all_named)
def test_path_with_ampersand(target, run):
    test_py = bp_root / "a&b" / "test.py"

    with debug.Session() as session:
        with run(session, target(test_py)):
            session.set_breakpoints(test_py, ["two"])

        session.wait_for_stop(
            "breakpoint", expected_frames=[some.dap.frame(test_py, line="two")]
        )
        session.request_continue()


@pytest.mark.skipif(
    sys.version_info < (3, 0), reason="Paths are not Unicode in Python 2.7"
)
@pytest.mark.skipif(
    sys.platform == "win32" and sys.version_info < (3, 6),
    reason="https://github.com/microsoft/ptvsd/issues/1124#issuecomment-459506802",
)
@pytest.mark.parametrize("target", targets.all_named)
def test_path_with_unicode(target, run):
    test_py = bp_root / "ನನ್ನ_ಸ್ಕ್ರಿಪ್ಟ್.py"

    with debug.Session() as session:
        with run(session, target(test_py)):
            session.set_breakpoints(test_py, ["bp"])

        session.wait_for_stop(
            "breakpoint",
            expected_frames=[some.dap.frame(test_py, name="ಏನಾದರೂ_ಮಾಡು", line="bp")],
        )
        session.request_continue()


conditions = {
    ("condition", "i==5"): lambda i: i == 5,
    ("hitCondition", "5"): lambda i: i == 5,
    ("hitCondition", "==5"): lambda i: i == 5,
    ("hitCondition", ">5"): lambda i: i > 5,
    ("hitCondition", ">=5"): lambda i: i >= 5,
    ("hitCondition", "<5"): lambda i: i < 5,
    ("hitCondition", "<=5"): lambda i: i <= 5,
    ("hitCondition", "%3"): lambda i: i % 3 == 0,
}


@pytest.mark.parametrize("condition_kind, condition", list(conditions.keys()))
@pytest.mark.parametrize("target", targets.all_named)
def test_conditional_breakpoint(pyfile, target, run, condition_kind, condition):
    hit = conditions[condition_kind, condition]

    @pyfile
    def code_to_debug():
        import debuggee

        debuggee.setup()
        for i in range(1, 10):
            print(i)  # @bp

    with debug.Session() as session:
        with run(session, target(code_to_debug)):
            session.request(
                "setBreakpoints",
                {
                    "source": {"path": code_to_debug},
                    "breakpoints": [
                        {"line": code_to_debug.lines["bp"], condition_kind: condition}
                    ],
                },
            )

        for i in range(1, 10):
            if not hit(i):
                continue
            session.wait_for_stop(
                expected_frames=[some.dap.frame(code_to_debug, line="bp")]
            )
            var_i = session.get_variable("i")
            assert var_i == some.dict.containing(
                {"name": "i", "evaluateName": "i", "type": "int", "value": str(i)}
            )
            session.request_continue()


def test_crossfile_breakpoint(pyfile, target, run):
    @pyfile
    def script1():
        import debuggee

        debuggee.setup()

        def do_something():
            print("do something")  # @bp

    @pyfile
    def script2():
        import debuggee
        import script1

        debuggee.setup()
        script1.do_something()  # @bp
        print("Done")

    with debug.Session() as session:
        with run(session, target(script2)):
            session.set_breakpoints(script1, all)
            session.set_breakpoints(script2, all)

        session.wait_for_stop(expected_frames=[some.dap.frame(script2, line="bp")])
        session.request_continue()

        session.wait_for_stop(expected_frames=[some.dap.frame(script1, line="bp")])
        session.request_continue()


# NameError in condition is a special case: pydevd is configured to skip traceback for
# name errors. See https://github.com/microsoft/ptvsd/issues/853 for more details. For
# all other errors, we should be printing traceback.
@pytest.mark.parametrize("error_name", ["NameError", ""])
def test_error_in_condition(pyfile, target, run, error_name):
    error_name = error_name or "ZeroDivisionError"

    condition, expect_traceback = {
        "NameError": ("no_such_name", False),
        "ZeroDivisionError": ("1 / 0", True),
    }[error_name]

    @pyfile
    def code_to_debug():
        import debuggee

        debuggee.setup()
        for i in range(1, 10):  # @bp
            pass

    with debug.Session() as session:
        with run(session, target(code_to_debug)):
            session.request(
                "setBreakpoints",
                {
                    "source": {"path": code_to_debug},
                    "breakpoints": [
                        {"line": code_to_debug.lines["bp"], "condition": condition}
                    ],
                },
            )

    if "internalConsole" not in str(run):
        assert not session.captured_stdout()

        error_name = error_name.encode("ascii")
        if expect_traceback:
            assert error_name in session.captured_stderr()
        else:
            assert error_name not in session.captured_stderr()


@pytest.mark.parametrize("condition", ["condition", ""])
@pytest.mark.parametrize("target", targets.all_named)
def test_log_point(pyfile, target, run, condition):
    @pyfile
    def code_to_debug():
        import debuggee
        import sys

        debuggee.setup()
        for i in range(0, 10):
            sys.stderr.write(str(i * 10) + "\n")  # @bp
            sys.stderr.flush()
        ()  # @wait_for_output

    lines = code_to_debug.lines
    with debug.Session() as session:
        session.config["redirectOutput"] = True

        with run(session, target(code_to_debug)):
            bp = {"line": lines["bp"], "logMessage": "{i}"}
            if condition:
                bp["condition"] = "i == 5"
            session.request(
                "setBreakpoints",
                {
                    "source": {"path": code_to_debug},
                    "breakpoints": [bp, {"line": lines["wait_for_output"]}],
                },
            )

        if condition:
            session.wait_for_stop(
                "breakpoint", expected_frames=[some.dap.frame(code_to_debug, line="bp")]
            )

            var_i = session.get_variable("i")
            assert var_i == some.dict.containing(
                {"name": "i", "evaluateName": "i", "type": "int", "value": "5"}
            )

            session.request_continue()

        session.wait_for_stop(
            "breakpoint",
            expected_frames=[some.dap.frame(code_to_debug, line="wait_for_output")],
        )
        session.request_continue()

    # print() should produce both actual output, and "output" events on stderr,
    # but logpoints should only produce "output" events on stdout.
    if "internalConsole" not in str(run):
        assert not session.captured_stdout()

    expected_stdout = "".join(
        (fmt(r"{0}\r?\n", re.escape(str(i))) for i in range(0, 10))
    )
    expected_stderr = "".join(
        (fmt(r"{0}\r?\n", re.escape(str(i * 10))) for i in range(0, 10))
    )
    assert session.output("stdout") == some.str.matching(expected_stdout)
    assert session.output("stderr") == some.str.matching(expected_stderr)


@pytest.mark.parametrize("run", [runners.launch])
def test_breakpoint_in_package_main(run):
    testpkgs = test_data / "testpkgs"
    main_py = testpkgs / "pkg1" / "__main__.py"

    with debug.Session() as session:
        session.expected_exit_code = 42
        session.config["cwd"] = testpkgs.strpath

        with run(session, targets.Module(name="pkg1")):
            session.set_breakpoints(main_py, ["two"])

        session.wait_for_stop(
            "breakpoint", expected_frames=[some.dap.frame(main_py, line="two")]
        )
        session.request_continue()


def test_add_and_remove_breakpoint(pyfile, target, run):
    @pyfile
    def code_to_debug():
        import debuggee

        debuggee.setup()
        for i in range(0, 10):
            print(i)  # @bp
        ()  # @wait_for_output

    with debug.Session() as session:
        session.config["redirectOutput"] = True

        with run(session, target(code_to_debug)):
            session.set_breakpoints(code_to_debug, all)

        session.wait_for_stop(
            "breakpoint", expected_frames=[some.dap.frame(code_to_debug, line="bp")]
        )

        # Remove breakpoint inside the loop.
        session.set_breakpoints(code_to_debug, ["wait_for_output"])
        session.request_continue()

        session.wait_for_stop(
            "breakpoint",
            expected_frames=[some.dap.frame(code_to_debug, line="wait_for_output")],
        )
        session.request_continue()

    expected_stdout = "".join((fmt("{0}\n", i) for i in range(0, 10)))
    assert session.output("stdout") == expected_stdout


def test_breakpoint_in_nonexistent_file(pyfile, target, run):
    @pyfile
    def code_to_debug():
        import debuggee

        debuggee.setup()

    with debug.Session() as session:
        with run(session, target(code_to_debug)):
            breakpoints = session.set_breakpoints("nonexistent_file.py", [1])
            assert breakpoints == [
                {
                    "verified": False,
                    "message": "Breakpoint in file that does not exist.",
                    "source": some.dict.containing(
                        {"path": some.path("nonexistent_file.py")}
                    ),
                    "line": 1,
                }
            ]


def test_invalid_breakpoints(pyfile, target, run):
    @pyfile
    def code_to_debug():
        import debuggee

        debuggee.setup()

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

    with debug.Session() as session:
        with run(session, target(code_to_debug)):
            bp_markers = ["bp1-requested", "bp2-requested", "bp3-requested"]
            if sys.version_info < (3,):
                bp_markers += ["bp4-requested-1", "bp4-requested-2"]

            bps = session.set_breakpoints(code_to_debug, bp_markers)
            actual_lines = [bp["line"] for bp in bps]

            if sys.version_info >= (3, 8):
                # See: https://bugs.python.org/issue38508
                expected_markers = ["bp1-expected", "bp2-requested", "bp3-expected"]
            else:
                expected_markers = ["bp1-expected", "bp2-expected", "bp3-expected"]
            if sys.version_info < (3,):
                expected_markers += ["bp4-expected", "bp4-expected"]
            expected_lines = [
                code_to_debug.lines[marker] for marker in expected_markers
            ]

            assert actual_lines == expected_lines

        # Now let's make sure that we hit all of the expected breakpoints,
        # and stop where we expect them to be.

        # If there's multiple breakpoints on the same line, we only stop once,
        # so remove duplicates first.
        expected_lines = sorted(set(expected_lines))
        if sys.version_info >= (3, 8):
            # We'll actually hit @bp3-expected and later @bp2-requested
            # (there's a line event when the list creation is finished
            # at the start of the list creation on 3.8).
            # See: https://bugs.python.org/issue38508
            expected_lines[1], expected_lines[2] = expected_lines[2], expected_lines[1]

        while expected_lines:
            expected_line = expected_lines.pop(0)
            session.wait_for_stop(
                "breakpoint",
                expected_frames=[some.dap.frame(code_to_debug, line=expected_line)],
            )
            session.request_continue()


def test_deep_stacks(pyfile, target, run):
    @pyfile
    def code_to_debug():
        import debuggee

        debuggee.setup()

        def deep_stack(level):
            if level <= 0:
                print("done")  # @bp
                return level
            deep_stack(level - 1)

        deep_stack(100)

    with debug.Session() as session:
        with run(session, target(code_to_debug)):
            session.set_breakpoints(code_to_debug, all)

        stop = session.wait_for_stop()
        assert len(stop.frames) > 100

        # Now try to retrieve the same stack in chunks, and check that it matches.
        frames = []
        for _ in range(5):
            stack_trace = session.request(
                "stackTrace",
                {"threadId": stop.thread_id, "startFrame": len(frames), "levels": 25},
            )

            assert stack_trace["totalFrames"] > 0
            frames += stack_trace["stackFrames"]

        assert stop.frames == frames
        session.request_continue()


@pytest.mark.parametrize("target", targets.all)
@pytest.mark.parametrize("func", ["breakpoint", "debugpy.breakpoint"])
def test_break_api(pyfile, target, run, func):
    if func == "breakpoint" and sys.version_info < (3, 7):
        pytest.skip("breakpoint() was introduced in Python 3.7")

    @pyfile
    def code_to_debug():
        import debuggee
        import debugpy  # noqa
        import sys

        debuggee.setup()
        func = eval(sys.argv[1])
        func()
        print("break here")  # @break

    with debug.Session() as session:
        target = target(code_to_debug, args=[func])
        with run(session, target):
            pass

        session.wait_for_stop(
            expected_frames=[some.dap.frame(target.source, target.lines["break"])]
        )
        session.request_continue()
