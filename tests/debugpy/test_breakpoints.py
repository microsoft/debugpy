# -*- coding: utf-8 -*-
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import pytest
import re
import sys

import tests
from tests import debug, test_data, timeline
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
    occurrences = session.timeline.all_occurrences_of(
        timeline.Event("output", some.dict.containing({"category": "important"})),
    )
    
    if expect_traceback:
        assert len(occurrences) == 10
        for occurrence in occurrences:
            assert error_name in occurrence.body['output']
    else:
        assert len(occurrences) == 0


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
        x = 4  # @wait_for_output

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

        session.wait_for_stop(
            "breakpoint",
            expected_frames=[some.dap.frame(code_to_debug, line="wait_for_output")],
        )
        session.request_continue()

    # print() should produce both actual output, and "output" events on stderr,
    # but logpoints should only produce "output" events on stdout.
    if "internalConsole" not in str(run):
        assert not session.captured_stdout()

    if condition:
        expected_stdout = "5\r?\n"
    else:
        expected_stdout = "".join(
            (r"{0}\r?\n".format(re.escape(str(i))) for i in range(0, 10))
        )
    expected_stderr = "".join(
        (r"{0}\r?\n".format(re.escape(str(i * 10))) for i in range(0, 10))
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
        x = 4  # @wait_for_output

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

    expected_stdout = "".join(f"{i}\n" for i in range(0, 10))
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
                    "id": 0,
                }
            ]


@pytest.mark.flaky(retries=2, delay=1)
def test_invalid_breakpoints(pyfile, target, run):
    @pyfile
    def code_to_debug():
        import debuggee

        debuggee.setup()

        # For markers below, rN = requested breakpoint, eN = expected breakpoint.
        # If there's no eN for some rN, it's assumed to be the same line.
        # fmt: off
        b = True
        while b:         # @e0-37,e0-38,e0-39
            pass         # @r0
            break

        print()         # @e1-37 
        [               # @r1,e2
            1, 2, 3,    # @e2-37,e2-38
        ]               # @r2

        print()         # @e3,e4
        print(1,        # @r3
              2, 3,     # @r4
              4, 5, 6)
        # fmt: on

    with debug.Session() as session:
        with run(session, target(code_to_debug)):
            requested_markers = ["r" + str(i) for i in range(0, 3)]

            bps = session.set_breakpoints(code_to_debug, requested_markers)
            actual_lines = [bp["line"] for bp in bps]

            expected_markers = []
            for r in requested_markers:
                e_generic = "e" + r[1:]
                e_versioned = (
                    e_generic
                    + "-"
                    + str(sys.version_info.major)
                    + str(sys.version_info.minor)
                )
                for e in e_versioned, e_generic, r:
                    if e in code_to_debug.lines:
                        expected_markers.append(e)
                        break

            expected_lines = [
                code_to_debug.lines[marker] for marker in expected_markers
            ]
            assert actual_lines == expected_lines

        # Now let's make sure that we hit all of the expected breakpoints,
        # and stop where we expect them to be.

        # If there's multiple breakpoints on the same line, we only stop once,
        # so remove duplicates first.
        expected_lines = sorted(set(expected_lines))
        if (3, 8) <= sys.version_info < (3, 9):
            # We'll actually hit @e2-38 first, and only then @r1, because there's
            # a line event for [ when the list creation is finished on 3.8).
            # See https://bugs.python.org/issue38508 for details.
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


def test_hit_breakpoint_ids(pyfile, target, run):
    @pyfile
    def code_to_debug():
        import debuggee

        debuggee.setup()
        print("first")  # @bp1
        print("second")  # @bp2

    with debug.Session() as session:
        with run(session, target(code_to_debug)):
            breakpoints = session.set_breakpoints(code_to_debug, ["bp1", "bp2"])
        bp1_id, bp2_id = (bp["id"] for bp in breakpoints)

        stop = session.wait_for_stop("breakpoint")
        assert stop.body["hitBreakpointIds"] == [bp1_id]
        session.request_continue()

        stop = session.wait_for_stop("breakpoint")
        assert stop.body["hitBreakpointIds"] == [bp2_id]
        session.request_continue()


def test_hit_breakpoint_ids_function_breakpoint(pyfile, target, run):
    @pyfile
    def code_to_debug():
        import debuggee

        debuggee.setup()

        def my_func():
            print("in my_func")

        my_func()

    with debug.Session() as session:
        with run(session, target(code_to_debug)):
            # The decoy is never called, so the reported id must be the second one
            # rather than merely the first id handed out.
            response = session.request(
                "setFunctionBreakpoints",
                {"breakpoints": [{"name": "decoy"}, {"name": "my_func"}]},
            )
        bp_id = response["breakpoints"][1]["id"]

        stop = session.wait_for_stop("function breakpoint")
        assert stop.body["hitBreakpointIds"] == [bp_id]
        session.request_continue()


def test_hit_breakpoint_ids_absent_on_later_stops(pyfile, target, run):
    @pyfile
    def code_to_debug():
        import debuggee
        import debugpy

        debuggee.setup()
        print("first")  # @bp
        print("second")
        debugpy.breakpoint()
        print("third")

    with debug.Session() as session:
        with run(session, target(code_to_debug)):
            breakpoints = session.set_breakpoints(code_to_debug, ["bp"])
        bp_id = breakpoints[0]["id"]

        stop = session.wait_for_stop("breakpoint")
        assert stop.body["hitBreakpointIds"] == [bp_id]

        session.request("next", {"threadId": stop.thread_id})
        stop = session.wait_for_stop("step")
        assert "hitBreakpointIds" not in stop.body
        session.request_continue()

        # debugpy.breakpoint() also reports reason "breakpoint", so the reason alone
        # cannot distinguish it: only clearing the ids on resume keeps this stop from
        # claiming the real breakpoint above was hit again.
        stop = session.wait_for_stop("breakpoint")
        assert "hitBreakpointIds" not in stop.body
        session.request_continue()


def test_hit_breakpoint_ids_per_thread_notification(pyfile, target, run):
    @pyfile
    def code_to_debug():
        import debuggee

        debuggee.setup()

        def never_called():
            print("decoy")  # @decoy

        print("first")  # @bp

    with debug.Session() as session:
        with run(session, target(code_to_debug)):
            # Exercises the per-thread stopped event, which is only built when threads
            # are reported individually. Must precede set_breakpoints: the suspend
            # policy is derived from this when each breakpoint is registered.
            session.request(
                "setDebuggerProperty", {"multiThreadsSingleNotification": False}
            )
            breakpoints = session.set_breakpoints(code_to_debug, ["decoy", "bp"])
        bp_id = breakpoints[1]["id"]

        # Not wait_for_stop, which asserts allThreadsStopped.
        stopped = session.wait_for_next_event("stopped")
        assert stopped["reason"] == "breakpoint"
        assert not stopped["allThreadsStopped"]
        assert stopped["hitBreakpointIds"] == [bp_id]

        session.request_continue()


def test_hit_breakpoint_ids_absent_when_line_is_ambiguous(pyfile, target, run):
    @pyfile
    def code_to_debug():
        import debuggee

        debuggee.setup()
        print("first")  # @bp
        # @ambiguous

    with debug.Session() as session:
        with run(session, target(code_to_debug)):
            breakpoints = session.set_breakpoints(code_to_debug, ["bp", "ambiguous"])

        # The comment line has no code, so it resolves back onto the line above and the
        # two breakpoints collapse into one.
        assert breakpoints[0]["line"] == breakpoints[1]["line"]

        stop = session.wait_for_stop("breakpoint")
        assert "hitBreakpointIds" not in stop.body
        session.request_continue()
