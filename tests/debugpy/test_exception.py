# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import pytest
import sys

from tests import debug
from tests.debug import runners, targets
from tests.patterns import some
from tests.timeline import Event

str_matching_ArithmeticError = some.str.matching(r"(.+\.)?ArithmeticError")


@pytest.mark.parametrize("raised", ["raised", ""])
@pytest.mark.parametrize("uncaught", ["uncaught", ""])
def test_vsc_exception_options_raise_with_except(pyfile, target, run, raised, uncaught):
    @pyfile
    def code_to_debug():
        import debuggee

        debuggee.setup()

        def raise_with_except():
            try:
                raise ArithmeticError("bad code")  # @exc
            except Exception:
                pass

        raise_with_except()

    with debug.Session() as session:
        session.expected_exit_code = some.int
        with run(session, target(code_to_debug)):
            session.request(
                "setExceptionBreakpoints", {"filters": list({raised, uncaught} - {""})}
            )

        expected = some.dict.containing(
            {
                "exceptionId": str_matching_ArithmeticError,
                "description": "bad code",
                "breakMode": "always" if raised else "unhandled",
                "details": some.dict.containing(
                    {
                        "typeName": str_matching_ArithmeticError,
                        "message": "bad code",
                        "source": some.path(code_to_debug),
                    }
                ),
            }
        )

        if raised:
            stop = session.wait_for_stop(
                "exception",
                expected_text=str_matching_ArithmeticError,
                expected_description="bad code",
                expected_frames=[some.dap.frame(code_to_debug, line="exc")],
            )
            exc_info = session.request("exceptionInfo", {"threadId": stop.thread_id})
            assert exc_info == expected
            session.request_continue()

        if uncaught:
            # Exception is caught by try..except, so there should be no stop.
            pass


@pytest.mark.parametrize("raised", ["raised", ""])
@pytest.mark.parametrize("uncaught", ["uncaught", ""])
def test_vsc_exception_options_raise_without_except(
    pyfile, target, run, raised, uncaught
):
    @pyfile
    def code_to_debug():
        import debuggee

        debuggee.setup()

        def raise_without_except():
            raise ArithmeticError("bad code")  # @exc

        raise_without_except()

    with debug.Session() as session:
        session.ignore_unobserved.append(Event("stopped"))
        session.expected_exit_code = some.int

        with run(session, target(code_to_debug)):
            session.request(
                "setExceptionBreakpoints", {"filters": list({raised, uncaught} - {""})}
            )

        expected_exc_info = some.dict.containing(
            {
                "exceptionId": str_matching_ArithmeticError,
                "description": "bad code",
                "breakMode": "always" if raised else "unhandled",
                "details": some.dict.containing(
                    {
                        "typeName": str_matching_ArithmeticError,
                        "message": "bad code",
                        "source": some.path(code_to_debug),
                    }
                ),
            }
        )

        if raised:
            stop = session.wait_for_stop(
                "exception", expected_frames=[some.dap.frame(code_to_debug, line="exc")]
            )
            exc_info = session.request("exceptionInfo", {"threadId": stop.thread_id})
            assert expected_exc_info == exc_info
            session.request_continue()

            # NOTE: debugger stops at each frame if raised and is uncaught
            # This behavior can be changed by updating 'notify_on_handled_exceptions'
            # setting we send to pydevd to notify only once. In our test code, we have
            # two frames, hence two stops.
            session.wait_for_stop("exception")
            session.request_continue()

        if uncaught:
            stop = session.wait_for_stop(
                "exception", expected_frames=[some.dap.frame(code_to_debug, line="exc")]
            )
            expected_exc_info = some.dict.containing(
                {
                    "exceptionId": str_matching_ArithmeticError,
                    "description": "bad code",
                    "breakMode": "unhandled",  # Only difference from previous expected is breakMode.
                    "details": some.dict.containing(
                        {
                            "typeName": str_matching_ArithmeticError,
                            "message": "bad code",
                            "source": some.path(code_to_debug),
                        }
                    ),
                }
            )
            exc_info = session.request("exceptionInfo", {"threadId": stop.thread_id})
            assert expected_exc_info == exc_info
            session.request_continue()


@pytest.mark.skipif(
    sys.platform == "darwin",
    reason="https://github.com/microsoft/ptvsd/issues/1988",
)
@pytest.mark.parametrize("target", targets.all_named)
@pytest.mark.parametrize("run", runners.all)
@pytest.mark.parametrize("raised", ["raised", ""])
@pytest.mark.parametrize("uncaught", ["uncaught", ""])
@pytest.mark.parametrize("zero", ["zero", ""])
@pytest.mark.parametrize("exit_code", [0, 1, "nan"])
def test_systemexit(pyfile, target, run, raised, uncaught, zero, exit_code):
    @pyfile
    def code_to_debug():
        import debuggee
        import sys

        debuggee.setup()
        exit_code = eval(sys.argv[1])
        print("sys.exit(%r)" % (exit_code,))
        try:
            sys.exit(exit_code)  # @handled
        except SystemExit:
            pass
        sys.exit(exit_code)  # @unhandled

    filters = []
    if raised:
        filters += ["raised"]
    if uncaught:
        filters += ["uncaught"]

    with debug.Session() as session:
        session.expected_exit_code = some.int
        session.config["breakOnSystemExitZero"] = bool(zero)

        with run(session, target(code_to_debug, args=[repr(exit_code)])):
            session.request("setExceptionBreakpoints", {"filters": filters})

        # When breaking on raised exceptions, we'll stop on both lines,
        # unless it's SystemExit(0) and we asked to ignore that.
        if raised and (zero or exit_code != 0):
            session.wait_for_stop(
                "exception",
                expected_frames=[some.dap.frame(code_to_debug, line="handled")],
            )
            session.request_continue()

            session.wait_for_stop(
                "exception",
                expected_frames=[some.dap.frame(code_to_debug, line="unhandled")],
            )
            session.request_continue()

        # When breaking on uncaught exceptions, we'll stop on the second line,
        # unless it's SystemExit(0) and we asked to ignore that.
        # Note that if both raised and uncaught filters are set, there will be
        # two stop for the second line - one for exception being raised, and one
        # for it unwinding the stack without finding a handler. The block above
        # takes care of the first stop, so here we just take care of the second.
        if uncaught and (zero or exit_code != 0):
            session.wait_for_stop(
                "exception",
                expected_frames=[some.dap.frame(code_to_debug, line="unhandled")],
            )
            session.request_continue()


@pytest.mark.parametrize(
    "break_mode", ["always", "never", "unhandled", "userUnhandled"]
)
@pytest.mark.parametrize(
    "exceptions",
    [
        ["RuntimeError"],
        ["AssertionError"],
        ["RuntimeError", "AssertionError"],
        [],  # Add the whole Python Exceptions category.
    ],
)
def test_raise_exception_options(pyfile, target, run, exceptions, break_mode):
    if break_mode in ("never", "unhandled", "userUnhandled"):
        expect_exceptions = []
        if break_mode != "never" and (not exceptions or "AssertionError" in exceptions):
            # Only AssertionError is raised in this use-case.
            expect_exceptions = ["AssertionError"]

        @pyfile
        def code_to_debug():
            import debuggee

            debuggee.setup()
            raise AssertionError()  # @AssertionError

    else:
        expect_exceptions = exceptions[:]
        if not expect_exceptions:
            # Deal with the Python Exceptions category
            expect_exceptions = ["RuntimeError", "AssertionError", "IndexError"]

        @pyfile
        def code_to_debug():
            import debuggee

            debuggee.setup()

            try:
                raise RuntimeError()  # @RuntimeError
            except RuntimeError:
                pass
            try:
                raise AssertionError()  # @AssertionError
            except AssertionError:
                pass
            try:
                raise IndexError()  # @IndexError
            except IndexError:
                pass

    with debug.Session() as session:
        session.ignore_unobserved.append(Event("stopped"))
        session.expected_exit_code = some.int

        with run(session, target(code_to_debug)):
            path = [{"names": ["Python Exceptions"]}]
            if exceptions:
                path.append({"names": exceptions})
            session.request(
                "setExceptionBreakpoints",
                {
                    "filters": [],  # Unused when exceptionOptions is passed.
                    "exceptionOptions": [
                        {
                            "path": path,
                            "breakMode": break_mode,  # Can be "never", "always", "unhandled", "userUnhandled"
                        }
                    ],
                },
            )

        for expected_exception in expect_exceptions:
            session.wait_for_stop(
                "exception",
                expected_frames=[
                    some.dap.frame(code_to_debug, line=expected_exception)
                ],
            )
            session.request_continue()


@pytest.mark.parametrize("target", targets.all_named)
@pytest.mark.parametrize("run", runners.all)
@pytest.mark.parametrize("exit_code", [0, 3])
@pytest.mark.parametrize("break_on_system_exit_zero", ["break_on_system_exit_zero", ""])
@pytest.mark.parametrize("django", ["django", ""])
def test_success_exitcodes(
    pyfile, target, run, exit_code, break_on_system_exit_zero, django
):
    @pyfile
    def code_to_debug():
        import debuggee
        import sys

        debuggee.setup()
        exit_code = eval(sys.argv[1])
        print("sys.exit(%r)" % (exit_code,))
        sys.exit(exit_code)

    with debug.Session() as session:
        session.expected_exit_code = some.int
        session.config["breakOnSystemExitZero"] = bool(break_on_system_exit_zero)
        session.config["django"] = bool(django)

        with run(session, target(code_to_debug, args=[repr(exit_code)])):
            session.request("setExceptionBreakpoints", {"filters": ["uncaught"]})

        if break_on_system_exit_zero or (not django and exit_code == 3):
            # If "breakOnSystemExitZero" was specified, we should always break.
            # Otherwise, we should not break if the exit code indicates successful
            # exit. 0 always indicates success, and 3 indicates failure only if
            # Django debugging wasn't enabled.
            session.wait_for_stop("exception")
            session.request_continue()


@pytest.mark.parametrize("max_frames", ["default", "all", 10])
def test_exception_stack(pyfile, target, run, max_frames):
    @pyfile
    def code_to_debug():
        import debuggee

        debuggee.setup()

        def do_something(n):
            if n <= 0:
                raise ArithmeticError("bad code")  # @unhandled
            do_something2(n - 1)

        def do_something2(n):
            do_something(n - 1)

        do_something(100)

    with debug.Session() as session:
        session.expected_exit_code = some.int

        max_frames, (min_expected_lines, max_expected_lines) = {
            "all": (0, (100, 221)),
            "default": (None, (100, 221)),
            10: (10, (10, 22)),
        }[max_frames]
        if max_frames is not None:
            session.config["maxExceptionStackFrames"] = max_frames

        with run(session, target(code_to_debug)):
            session.request("setExceptionBreakpoints", {"filters": ["uncaught"]})

        stop = session.wait_for_stop(
            "exception",
            expected_frames=[some.dap.frame(code_to_debug, line="unhandled")],
        )
        exc_info = session.request("exceptionInfo", {"threadId": stop.thread_id})
        expected_exc_info = some.dict.containing(
            {
                "exceptionId": str_matching_ArithmeticError,
                "description": "bad code",
                "breakMode": "unhandled",
                "details": some.dict.containing(
                    {
                        "typeName": str_matching_ArithmeticError,
                        "message": "bad code",
                        "source": some.path(code_to_debug),
                    }
                ),
            }
        )
        assert expected_exc_info == exc_info
        stack_str = exc_info["details"]["stackTrace"]
        stack_line_count = len(stack_str.split("\n"))
        assert min_expected_lines <= stack_line_count <= max_expected_lines

        session.request_continue()
