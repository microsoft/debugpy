# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import pytest

from tests import debug, start_methods
from tests.patterns import some


@pytest.mark.parametrize("breakpoint", ["breakpoint", ""])
def test_stop_on_entry(pyfile, run_as, breakpoint):
    @pyfile
    def code_to_debug():
        from debug_me import backchannel  # @bp

        backchannel.send("done")

    with debug.Session(start_methods.Launch, backchannel=True) as session:
        backchannel = session.backchannel
        session.configure(
            run_as, code_to_debug,
            stopOnEntry=True,
        )
        if breakpoint:
            session.set_breakpoints(code_to_debug, all)
        session.start_debugging()

        if breakpoint:
            hit = session.wait_for_stop(reason="breakpoint")
            assert hit.frames[0]["line"] == 1
            assert hit.frames[0]["source"]["path"] == some.path(code_to_debug)

            session.send_request("next", {"threadId": hit.thread_id}).wait_for_response()
            hit = session.wait_for_stop(reason="step")
            assert hit.frames[0]["line"] == 3
            assert hit.frames[0]["source"]["path"] == some.path(code_to_debug)
        else:
            hit = session.wait_for_stop(reason="entry")
            assert hit.frames[0]["line"] == 1
            assert hit.frames[0]["source"]["path"] == some.path(code_to_debug)

        session.request_continue()
        session.wait_for_termination()

        assert backchannel.receive() == "done"

        session.stop_debugging()
