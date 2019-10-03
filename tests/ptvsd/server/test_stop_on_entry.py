# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import pytest

from tests import debug
from tests.debug import runners
from tests.patterns import some


@pytest.mark.parametrize("breakpoint", ["breakpoint", ""])
@pytest.mark.parametrize("run", runners.all_launch)
def test_stop_on_entry(pyfile, run, target, breakpoint):
    @pyfile
    def code_to_debug():
        from debug_me import backchannel  # @bp

        backchannel.send("done")

    with debug.Session() as session:
        session.config["stopOnEntry"] = True

        backchannel = session.open_backchannel()
        with run(session, target(code_to_debug)):
            if breakpoint:
                session.set_breakpoints(code_to_debug, all)

        if breakpoint:
            stop = session.wait_for_stop(
                "breakpoint", expected_frames=[some.dap.frame(code_to_debug, 1)]
            )
            session.request("next", {"threadId": stop.thread_id})
            stop = session.wait_for_stop(
                "step", expected_frames=[some.dap.frame(code_to_debug, 3)]
            )
        else:
            session.wait_for_stop(
                "entry", expected_frames=[some.dap.frame(code_to_debug, 1)]
            )

        session.request_continue()
        assert backchannel.receive() == "done"
