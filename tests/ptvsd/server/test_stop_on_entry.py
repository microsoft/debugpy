# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import pytest

from tests import debug
from tests.patterns import some


@pytest.mark.parametrize("start_method", ["launch"])
@pytest.mark.parametrize("with_bp", ["with_breakpoint", ""])
def test_stop_on_entry(pyfile, start_method, run_as, with_bp):
    @pyfile
    def code_to_debug():
        from debug_me import backchannel  # @bp

        backchannel.send("done")

    with debug.Session() as session:
        backchannel = session.setup_backchannel()
        session.initialize(
            target=(run_as, code_to_debug),
            start_method=start_method,
            debug_options=["StopOnEntry"],
            use_backchannel=True,
        )
        if bool(with_bp):
            session.set_breakpoints(code_to_debug, [code_to_debug.lines["bp"]])

        session.start_debugging()

        if bool(with_bp):
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

        session.wait_for_exit()
