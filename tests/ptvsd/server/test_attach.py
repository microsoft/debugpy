# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import pytest

from tests import debug, test_data
from tests.patterns import some
from tests.timeline import Event


@pytest.mark.parametrize("wait_for_attach", ["wait_for_attach", ""])
@pytest.mark.parametrize("is_attached", ["is_attached", ""])
@pytest.mark.parametrize("break_into_debugger", ["break_into_debugger", ""])
def test_attach(run_as, wait_for_attach, is_attached, break_into_debugger):
    attach1_py = test_data / "attach" / "attach1.py"

    with debug.Session("custom_server") as session:
        session.env.update({
            "ATTACH1_TEST_PORT": str(session.ptvsd_port),
            "ATTACH1_WAIT_FOR_ATTACH": "1" if wait_for_attach else "0",
            "ATTACH1_IS_ATTACHED":  "1" if is_attached else "0",
            "ATTACH1_BREAK_INTO_DEBUGGER": "1" if break_into_debugger else "0",
        })

        backchannel = session.setup_backchannel()
        session.initialize(target=(run_as, attach1_py))
        session.start_debugging()

        if wait_for_attach:
            assert backchannel.receive() == "wait_for_attach"

        if is_attached:
            assert backchannel.receive() == "is_attached"

        if break_into_debugger:
            assert backchannel.receive() == "break_into_debugger?"
            backchannel.send("proceed")
            session.wait_for_stop(expected_frames=[
                some.dap.frame(attach1_py, "break_into_debugger")
            ])
        else:
            assert backchannel.receive() == "loop?"
            backchannel.send("proceed")
            session.request("pause", freeze=False)
            session.wait_for_stop("pause")
            session.scratchpad["paused"] = True

        session.request_continue()
        session.wait_for_exit()


@pytest.mark.parametrize(
    "start_method", ["attach_socket_cmdline", "attach_socket_import"]
)
# @pytest.mark.skip(reason="Test fails often in local runs. Uncomment as needed.")
def test_reattach(pyfile, start_method, run_as):
    @pyfile
    def code_to_debug():
        from debug_me import ptvsd, scratchpad
        import time

        ptvsd.break_into_debugger()
        object()  # @first

        scratchpad["exit"] = False
        while not scratchpad["exit"]:
            time.sleep(0.1)
            ptvsd.break_into_debugger()
            object()  # @second

    with debug.Session(start_method) as session:
        session.initialize(
            target=(run_as, code_to_debug),
            kill_ptvsd=False,
            capture_output=False,
        )
        session.start_debugging()
        session.wait_for_stop(expected_frames=[
            some.dap.frame(code_to_debug, "first"),
        ])
        session.request_disconnect()
        session.wait_for_disconnect()

    with session.reattach(target=(run_as, code_to_debug)) as session2:
        session2.start_debugging()
        session2.wait_for_stop(expected_frames=[
            some.dap.frame(code_to_debug, "second"),
        ])
        session.scratchpad["exit"] = True
        session.request_disconnect()
        session.wait_for_disconnect()


@pytest.mark.parametrize("start_method", ["attach_pid"])
@pytest.mark.parametrize("run_as", ["file", "module", "code"])
@pytest.mark.skip(reason="Enable after #846, #863 and #1144 are fixed")
def test_attaching_by_pid(pyfile, run_as, start_method):
    @pyfile
    def code_to_debug():
        import debug_me  # noqa
        import time

        def do_something(i):
            time.sleep(0.1)
            print(i)  # @bp

        for i in range(100):
            do_something(i)

    with debug.Session(start_method) as session:
        session.initialize(target=(run_as, code_to_debug))
        session.set_breakpoints(code_to_debug, all)
        session.start_debugging()

        session.wait_for_stop(expected_frames=[
            some.dap.frame(code_to_debug, "bp"),
        ])

        # Remove breakpoint and continue.
        session.set_breakpoints(code_to_debug, [])
        session.request_continue()
        session.wait_for_next(
            Event("output", some.dict.containing({"category": "stdout"}))
        )

        session.wait_for_exit()
