# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import pytest

from tests import debug
from tests.debug import targets
from tests.patterns import some


@pytest.mark.parametrize("jmc", ["jmc", ""])
@pytest.mark.parametrize("target", targets.all_named)
def test_justmycode_frames(pyfile, target, run, jmc):
    @pyfile
    def code_to_debug():
        import debuggee

        debuggee.setup()

        import this  # @bp

        assert this

    with debug.Session() as session:
        session.config["justMyCode"] = bool(jmc)

        with run(session, target(code_to_debug)):
            session.set_breakpoints(code_to_debug, all)

        stop = session.wait_for_stop(
            "breakpoint", expected_frames=[some.dap.frame(code_to_debug, "bp")]
        )
        if jmc:
            assert len(stop.frames) == 1
        else:
            assert len(stop.frames) >= 1

        session.request("stepIn", {"threadId": stop.thread_id})

        # With JMC, it should step out of the function, remaining in the same file.
        # Without JMC, it should step into stdlib.
        expected_path = some.path(code_to_debug)
        if not jmc:
            expected_path = ~expected_path
        session.wait_for_stop(
            "step",
            expected_frames=[some.dap.frame(some.dap.source(expected_path), some.int)],
        )

        session.request_continue()
