# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.
import pytest

from tests import debug
from tests.patterns import some
from tests.timeline import Event


def test_post_mortem_basic(pyfile, target, run):
    """Calling post_mortem() inside an except block should stop the debugger."""

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
            debugpy.post_mortem()

    with debug.Session() as session:
        with run(session, target(code_to_debug)):
            session.request("setExceptionBreakpoints", {"filters": ["uncaught"]})

        occ = session.wait_for_next(
            Event("stopped") | Event("terminated"),
        )

        if occ.event == "terminated":
            pytest.fail("Debuggee exited without hitting breakpoint")
        
        exc_info = session.request("exceptionInfo", {"threadId": occ.body['threadId']})
        assert exc_info == some.dict.containing(
            {
                "exceptionId": some.str.matching(r"(.+\.)?ValueError"),
                "description": "something went wrong",
                "breakMode": "unhandled",
            }
        )

        session.request_continue()

def test_post_mortem_basic_no_uncaught_breakpoint(pyfile, target, run):
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
            debugpy.post_mortem()

    with debug.Session() as session:
        with run(session, target(code_to_debug)):
            session.request("setExceptionBreakpoints", {"filters": []})

        occ = session.wait_for_next(
            Event("stopped") | Event("terminated"),
        )

        assert occ.event == "terminated", "Expected debuggee to exit without hitting breakpoint"

def test_post_mortem_excinfo(pyfile, target, run):
    """We can call post_mortem with an excinfo afterwards too."""

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
        
        print("About to call post_mortem with excinfo")
        debugpy.post_mortem(excinfo)
        

    with debug.Session() as session:
        with run(session, target(code_to_debug)):
            session.request("setExceptionBreakpoints", {"filters": ["uncaught"]})

        occ = session.wait_for_next(
            Event("stopped") | Event("terminated"),
        )

        if occ.event == "terminated":
            pytest.fail("Debuggee exited without hitting breakpoint")
        

        exc_info = session.request("exceptionInfo", {"threadId": occ.body['threadId']})
        assert exc_info == some.dict.containing(
            {
                "exceptionId": some.str.matching(r"(.+\.)?ValueError"),
                "description": "something went wrong",
                "breakMode": "unhandled",
            }
        )

        session.request_continue()

def test_post_mortem_not_as_uncaught(pyfile, target, run):
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
            debugpy.post_mortem(as_uncaught=False)
        

    with debug.Session() as session:
        with run(session, target(code_to_debug)):
            session.request("setExceptionBreakpoints", {"filters": []})

        occ = session.wait_for_next(
            Event("stopped") | Event("terminated"),
        )

        if occ.event == "terminated":
            pytest.fail("Debuggee exited without hitting breakpoint")
        
        exc_info = session.request("exceptionInfo", {"threadId": occ.body['threadId']})
        assert exc_info == some.dict.containing(
            {
                "exceptionId": some.str.matching(r"(.+\.)?ValueError"),
                "description": "something went wrong",
                "breakMode": "unhandled",
            }
        )

        session.request_continue()
