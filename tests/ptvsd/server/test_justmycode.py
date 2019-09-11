# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import pytest

from tests import debug
from tests.patterns import some


@pytest.mark.parametrize("jmc", ["jmc", ""])
def test_justmycode_frames(pyfile, start_method, run_as, jmc):
    @pyfile
    def code_to_debug():
        import debug_me  # noqa

        print("break here")  # @bp

    with debug.Session(start_method) as session:
        session.configure(run_as, code_to_debug, justMyCode=bool(jmc))
        session.set_breakpoints(code_to_debug, all)

        session.start_debugging()
        stop = session.wait_for_stop(
                "breakpoint",
                expected_frames=[
                    some.dap.frame(code_to_debug, "bp")
                ],
        )
        if jmc:
            assert len(stop.frames) == 1
        else:
            assert len(stop.frames) >= 1

        session.request("stepIn", {"threadId": stop.thread_id})

        if not jmc:
            # "stepIn" should stop somewhere inside stdlib
            session.wait_for_stop(
                "step",
                expected_frames=[
                    some.dap.frame(~some.str.equal_to(code_to_debug), some.int)
                ],
            )
            session.request_continue()
