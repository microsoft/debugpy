# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.
import pytest

from tests import debug
from tests.patterns import some
from tests.timeline import Event


def test_trigger_exception_handler_basic(pyfile, target, run):
    """Calling trigger_exception_handler() inside an except block should stop the debugger."""

    @pyfile
    def code_to_debug():
        import debuggee

        debuggee.setup()

        import debugpy

        def risky_operation():
            raise ValueError("something went wrong")  # @raise

        try:
            risky_operation()
        except ValueError:
            debugpy.trigger_exception_handler()

    with debug.Session() as session:
        with run(session, target(code_to_debug)):
            session.request("setExceptionBreakpoints", {"filters": ["uncaught"]})

        occ = session.wait_for_next(
            Event("stopped") | Event("terminated"),
        )

        if occ.event == "terminated":
            pytest.fail("Debuggee exited without hitting breakpoint")

        exc_info = session.request("exceptionInfo", {"threadId": occ.body["threadId"]})
        assert exc_info == some.dict.containing(
            {
                "exceptionId": some.str.matching(r"(.+\.)?ValueError"),
                "description": "something went wrong",
                "breakMode": "unhandled",
            }
        )

        session.request_continue()


def test_trigger_exception_handler_basic_with_exception(pyfile, target, run):
    """Can call trigger_exception_handler(e) with an exception alone."""

    @pyfile
    def code_to_debug():
        import debuggee

        debuggee.setup()

        import debugpy

        def risky_operation():
            raise ValueError("something went wrong")  # @raise

        try:
            risky_operation()
        except ValueError as e:
            debugpy.trigger_exception_handler(e)

    with debug.Session() as session:
        with run(session, target(code_to_debug)):
            session.request("setExceptionBreakpoints", {"filters": ["uncaught"]})

        occ = session.wait_for_next(
            Event("stopped") | Event("terminated"),
        )

        if occ.event == "terminated":
            pytest.fail("Debuggee exited without hitting breakpoint")

        exc_info = session.request("exceptionInfo", {"threadId": occ.body["threadId"]})
        assert exc_info == some.dict.containing(
            {
                "exceptionId": some.str.matching(r"(.+\.)?ValueError"),
                "description": "something went wrong",
                "breakMode": "unhandled",
            }
        )

        session.request_continue()


def test_trigger_exception_handler_basic_no_uncaught_breakpoint(pyfile, target, run):
    """We don't stop if the uncaught exception breakpoint isn't set."""

    @pyfile
    def code_to_debug():
        import debuggee

        debuggee.setup()

        import debugpy

        def risky_operation():
            raise ValueError("something went wrong")  # @raise

        try:
            risky_operation()
        except ValueError:
            debugpy.trigger_exception_handler()

    with debug.Session() as session:
        with run(session, target(code_to_debug)):
            session.request("setExceptionBreakpoints", {"filters": []})

        occ = session.wait_for_next(
            Event("stopped") | Event("terminated"),
        )

        assert (
            occ.event == "terminated"
        ), "Expected debuggee to exit without hitting breakpoint"


def test_trigger_exception_handler_excinfo(pyfile, target, run):
    """We can call trigger_exception_handler with an excinfo afterwards too."""

    @pyfile
    def code_to_debug():
        import sys

        import debuggee

        debuggee.setup()

        import debugpy

        def risky_operation():
            raise ValueError("something went wrong")  # @raise

        try:
            risky_operation()
        except ValueError:
            excinfo = sys.exc_info()

        debugpy.trigger_exception_handler(excinfo)

    with debug.Session() as session:
        with run(session, target(code_to_debug)):
            session.request("setExceptionBreakpoints", {"filters": ["uncaught"]})

        occ = session.wait_for_next(
            Event("stopped") | Event("terminated"),
        )

        if occ.event == "terminated":
            pytest.fail("Debuggee exited without hitting breakpoint")

        exc_info = session.request("exceptionInfo", {"threadId": occ.body["threadId"]})
        assert exc_info == some.dict.containing(
            {
                "exceptionId": some.str.matching(r"(.+\.)?ValueError"),
                "description": "something went wrong",
                "breakMode": "unhandled",
            }
        )

        session.request_continue()


def test_trigger_exception_handler_restores_tracing(pyfile, target, run):
    """Breakpoints on the same thread must still work after resuming from the stop."""

    @pyfile
    def code_to_debug():
        import debuggee

        debuggee.setup()

        import debugpy

        def risky_operation():
            raise ValueError("something went wrong")  # @raise

        try:
            risky_operation()
        except ValueError:
            debugpy.trigger_exception_handler()

        print("check here")  # @bp

    with debug.Session() as session:
        with run(session, target(code_to_debug)):
            session.request("setExceptionBreakpoints", {"filters": ["uncaught"]})
            session.set_breakpoints(code_to_debug, ["bp"])

        session.wait_for_stop("exception")
        session.request_continue()

        session.wait_for_stop(
            "breakpoint",
            expected_frames=[some.dap.frame(code_to_debug, line="bp")],
        )
        session.request_continue()


def test_trigger_exception_handler_no_op_paths(pyfile, target, run):
    """Bad input raises ValueError; calling with no current exception is a no-op."""

    @pyfile
    def code_to_debug():
        import sys

        import debuggee

        debuggee.setup()

        import debugpy

        try:
            debugpy.trigger_exception_handler("not an exception")
            sys.exit(1)  # should have raised ValueError
        except ValueError:
            pass

        # No current exception -> no-op.
        debugpy.trigger_exception_handler()

        # No traceback -> no-op.
        debugpy.trigger_exception_handler(ValueError("never raised"))

    with debug.Session() as session:
        with run(session, target(code_to_debug)):
            session.request("setExceptionBreakpoints", {"filters": []})

        occ = session.wait_for_next(
            Event("stopped") | Event("terminated"),
        )

        assert occ.event == "terminated", "Expected debuggee to exit without stopping"


def test_trigger_exception_handler_not_as_uncaught(pyfile, target, run):
    """Setting as_uncaught=False enters postmortem debugging even if the uncaught exception breakpoint isn't set."""

    @pyfile
    def code_to_debug():
        import debuggee

        debuggee.setup()

        import debugpy

        def risky_operation():
            raise ValueError("something went wrong")  # @raise

        try:
            risky_operation()
        except ValueError:
            debugpy.trigger_exception_handler(as_uncaught=False)

    with debug.Session() as session:
        with run(session, target(code_to_debug)):
            session.request("setExceptionBreakpoints", {"filters": []})

        occ = session.wait_for_next(
            Event("stopped") | Event("terminated"),
        )

        if occ.event == "terminated":
            pytest.fail("Debuggee exited without hitting breakpoint")

        exc_info = session.request("exceptionInfo", {"threadId": occ.body["threadId"]})
        assert exc_info == some.dict.containing(
            {
                "exceptionId": some.str.matching(r"(.+\.)?ValueError"),
                "description": "something went wrong",
                "breakMode": "unhandled",
            }
        )

        session.request_continue()
