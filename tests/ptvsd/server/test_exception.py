# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import pytest

from tests import debug
from tests.patterns import some
from tests.timeline import Event

str_matching_ArithmeticError = some.str.matching(r"(.+\.)?ArithmeticError")


@pytest.mark.parametrize("raised", ["raisedOn", "raisedOff"])
@pytest.mark.parametrize("uncaught", ["uncaughtOn", "uncaughtOff"])
def test_vsc_exception_options_raise_with_except(
    pyfile, start_method, run_as, raised, uncaught
):
    @pyfile
    def code_to_debug():
        import debug_me  # noqa

        def raise_with_except():
            try:
                raise ArithmeticError("bad code")  # @exception_line
            except Exception:
                pass

        raise_with_except()

    ex_line = code_to_debug.lines["exception_line"]
    filters = []
    filters += ["raised"] if raised == "raisedOn" else []
    filters += ["uncaught"] if uncaught == "uncaughtOn" else []

    with debug.Session(start_method) as session:
        session.expected_exit_code = some.int
        session.configure(run_as, code_to_debug)
        session.request("setExceptionBreakpoints", {"filters": filters})
        session.start_debugging()

        expected = some.dict.containing(
            {
                "exceptionId": str_matching_ArithmeticError,
                "description": "bad code",
                "breakMode": "always" if raised == "raisedOn" else "unhandled",
                "details": some.dict.containing(
                    {
                        "typeName": str_matching_ArithmeticError,
                        "message": "bad code",
                        "source": some.path(code_to_debug),
                    }
                ),
            }
        )

        if raised == "raisedOn":
            hit = session.wait_for_stop(
                "exception",
                expected_text=str_matching_ArithmeticError,
                expected_description="bad code",
            )
            assert ex_line == hit.frames[0]["line"]

            resp_exc_info = session.send_request(
                "exceptionInfo", {"threadId": hit.thread_id}
            ).wait_for_response()

            assert resp_exc_info.body == expected
            session.request_continue()

        # uncaught should not 'stop' matter since the exception is caught


@pytest.mark.parametrize("raised", ["raisedOn", "raisedOff"])
@pytest.mark.parametrize("uncaught", ["uncaughtOn", "uncaughtOff"])
def test_vsc_exception_options_raise_without_except(
    pyfile, start_method, run_as, raised, uncaught
):
    @pyfile
    def code_to_debug():
        import debug_me  # noqa

        def raise_without_except():
            raise ArithmeticError("bad code")  # @exception_line

        raise_without_except()

    ex_line = code_to_debug.lines["exception_line"]
    filters = []
    filters += ["raised"] if raised == "raisedOn" else []
    filters += ["uncaught"] if uncaught == "uncaughtOn" else []
    with debug.Session(start_method) as session:
        session.ignore_unobserved += [Event("stopped")]
        session.expected_exit_code = some.int
        session.configure(run_as, code_to_debug)
        session.send_request(
            "setExceptionBreakpoints", {"filters": filters}
        ).wait_for_response()
        session.start_debugging()

        expected = some.dict.containing(
            {
                "exceptionId": str_matching_ArithmeticError,
                "description": "bad code",
                "breakMode": "always" if raised == "raisedOn" else "unhandled",
                "details": some.dict.containing(
                    {
                        "typeName": str_matching_ArithmeticError,
                        "message": "bad code",
                        "source": some.path(code_to_debug),
                    }
                ),
            }
        )

        if raised == "raisedOn":
            hit = session.wait_for_stop("exception")
            assert ex_line == hit.frames[0]["line"]

            resp_exc_info = session.send_request(
                "exceptionInfo", {"threadId": hit.thread_id}
            ).wait_for_response()

            assert resp_exc_info.body == expected
            session.request_continue()

            # NOTE: debugger stops at each frame if raised and is uncaught
            # This behavior can be changed by updating 'notify_on_handled_exceptions'
            # setting we send to pydevd to notify only once. In our test code, we have
            # two frames, hence two stops.
            session.wait_for_stop("exception")
            session.request_continue()

        if uncaught == "uncaughtOn":
            hit = session.wait_for_stop("exception")
            assert ex_line == hit.frames[0]["line"]

            resp_exc_info = session.send_request(
                "exceptionInfo", {"threadId": hit.thread_id}
            ).wait_for_response()

            expected = some.dict.containing(
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

            assert resp_exc_info.body == expected
            session.request_continue()


@pytest.mark.parametrize("raised", ["raised", ""])
@pytest.mark.parametrize("uncaught", ["uncaught", ""])
@pytest.mark.parametrize("zero", ["zero", ""])
@pytest.mark.parametrize("exit_code", [0, 1, "nan"])
def test_systemexit(pyfile, start_method, run_as, raised, uncaught, zero, exit_code):
    @pyfile
    def code_to_debug():
        import debug_me  # noqa
        import sys

        exit_code = eval(sys.argv[1])
        print("sys.exit(%r)" % (exit_code,))
        try:
            sys.exit(exit_code)  # @handled
        except SystemExit:
            pass
        sys.exit(exit_code)  # @unhandled

    line_numbers = code_to_debug.lines

    filters = []
    if raised:
        filters += ["raised"]
    if uncaught:
        filters += ["uncaught"]

    with debug.Session(start_method) as session:
        session.expected_exit_code = some.int
        session.configure(run_as, code_to_debug, args=[repr(exit_code)], breakOnSystemExitZero=bool(zero))
        session.send_request(
            "setExceptionBreakpoints", {"filters": filters}
        ).wait_for_response()
        session.start_debugging()

        # When breaking on raised exceptions, we'll stop on both lines,
        # unless it's SystemExit(0) and we asked to ignore that.
        if raised and (zero or exit_code != 0):
            hit = session.wait_for_stop("exception")
            assert hit.frames[0]["line"] == line_numbers["handled"]
            session.request_continue()

            hit = session.wait_for_stop("exception")
            assert hit.frames[0]["line"] == line_numbers["unhandled"]
            session.request_continue()

        # When breaking on uncaught exceptions, we'll stop on the second line,
        # unless it's SystemExit(0) and we asked to ignore that.
        # Note that if both raised and uncaught filters are set, there will be
        # two stop for the second line - one for exception being raised, and one
        # for it unwinding the stack without finding a handler. The block above
        # takes care of the first stop, so here we just take care of the second.
        if uncaught and (zero or exit_code != 0):
            hit = session.wait_for_stop("exception")
            assert hit.frames[0]["line"] == line_numbers["unhandled"]
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
def test_raise_exception_options(pyfile, start_method, run_as, exceptions, break_mode):

    if break_mode in ("never", "unhandled", "userUnhandled"):

        @pyfile
        def code_to_debug():
            import debug_me  # noqa

            raise AssertionError()  # @AssertionError

        if break_mode == "never":
            expect_exceptions = []

        elif "AssertionError" in exceptions or not exceptions:
            # Only AssertionError is raised in this use-case.
            expect_exceptions = ["AssertionError"]

        else:
            expect_exceptions = []

    else:
        expect_exceptions = exceptions[:]
        if not expect_exceptions:
            # Deal with the Python Exceptions category
            expect_exceptions = ["RuntimeError", "AssertionError", "IndexError"]

        @pyfile
        def code_to_debug():
            import debug_me  # noqa

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

    with debug.Session(start_method) as session:
        session.ignore_unobserved += [Event("stopped")]
        session.expected_exit_code = some.int
        session.configure(run_as, code_to_debug)
        path = [{"names": ["Python Exceptions"]}]
        if exceptions:
            path.append({"names": exceptions})
        session.send_request(
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
        ).wait_for_response()
        session.start_debugging()

        for expected_exception in expect_exceptions:
            hit = session.wait_for_stop("exception")
            assert hit.frames[0]["source"]["path"].endswith("code_to_debug.py")
            assert hit.frames[0]["line"] == code_to_debug.lines[expected_exception]
            session.request_continue()


@pytest.mark.parametrize("exit_code", [0, 3])
@pytest.mark.parametrize('break_on_system_exit_zero', [True, False])
@pytest.mark.parametrize('expect_django', [True, False])
def test_success_exitcodes(
    pyfile, start_method, run_as, exit_code, break_on_system_exit_zero, expect_django):
    @pyfile
    def code_to_debug():
        import debug_me  # noqa
        import sys

        exit_code = eval(sys.argv[1])
        print("sys.exit(%r)" % (exit_code,))
        sys.exit(exit_code)

    with debug.Session(start_method) as session:
        session.expected_exit_code = some.int
        session.configure(
            run_as,
            code_to_debug,
            args=[repr(exit_code)],
            successExitCodes=[3],
            breakOnSystemExitZero=break_on_system_exit_zero,
            django=expect_django
        )
        session.send_request(
            "setExceptionBreakpoints", {"filters": ["uncaught"]}
        ).wait_for_response()
        session.start_debugging()

        if break_on_system_exit_zero or (not expect_django and exit_code == 3):
            # If break_on_system_exit_zero, we should always break.
            # Otherwise, we should not break on system exit considered successful
            # (which means that we should break only in the case where
            # exit_code == 3 and django is not expected).

            session.wait_for_stop("exception")
            session.request_continue()


@pytest.mark.parametrize("max_frames", ["default", "all", 10])
def test_exception_stack(pyfile, start_method, run_as, max_frames):
    @pyfile
    def code_to_debug():
        import debug_me  # noqa

        def do_something(n):
            if n <= 0:
                raise ArithmeticError("bad code")  # @unhandled
            do_something2(n - 1)

        def do_something2(n):
            do_something(n - 1)

        do_something(100)

    maxFrames = None
    if max_frames == "all":
        # trace back compresses repeated text
        min_expected_lines = 100
        max_expected_lines = 221
        maxFrames = 0
    elif max_frames == "default":
        # default is all frames
        min_expected_lines = 100
        max_expected_lines = 221
        maxFrames = None
    else:
        min_expected_lines = 10
        max_expected_lines = 21
        maxFrames = 10

    with debug.Session(start_method) as session:
        session.expected_exit_code = some.int
        session.configure(
            run_as, code_to_debug,
            maxExceptionStackFrames=maxFrames,
        )
        session.send_request(
            "setExceptionBreakpoints", {"filters": ["uncaught"]}
        ).wait_for_response()
        session.start_debugging()

        hit = session.wait_for_stop("exception")
        assert hit.frames[0]["line"] == code_to_debug.lines["unhandled"]

        resp_exc_info = session.send_request(
            "exceptionInfo", {"threadId": hit.thread_id}
        ).wait_for_response()

        expected = some.dict.containing(
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
        assert resp_exc_info.body == expected
        stack_str = resp_exc_info.body["details"]["stackTrace"]
        stack_line_count = len(stack_str.split("\n"))
        assert min_expected_lines <= stack_line_count <= max_expected_lines

        session.request_continue()
