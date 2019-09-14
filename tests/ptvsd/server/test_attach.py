# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import pytest

from tests import debug
from tests.debug import runners, targets
from tests.patterns import some
from tests.timeline import Event


@pytest.mark.parametrize("stop_method", ["break_into_debugger", "pause"])
@pytest.mark.parametrize("is_attached", ["is_attached", ""])
@pytest.mark.parametrize("wait_for_attach", ["wait_for_attach", ""])
@pytest.mark.parametrize("target", targets.all)
def test_attach_api(pyfile, target, wait_for_attach, is_attached, stop_method):
    @pyfile
    def code_to_debug():
        from debug_me import backchannel, ptvsd, scratchpad
        import sys
        import time

        _, host, port, wait_for_attach, is_attached, stop_method = sys.argv
        port = int(port)
        ptvsd.enable_attach((host, port))

        if wait_for_attach:
            backchannel.send("wait_for_attach")
            ptvsd.wait_for_attach()

        if is_attached:
            backchannel.send("is_attached")
            while not ptvsd.is_attached():
                print("looping until is_attached")
                time.sleep(0.1)

        if stop_method == "break_into_debugger":
            backchannel.send("break_into_debugger?")
            assert backchannel.receive() == "proceed"
            ptvsd.break_into_debugger()
            print("break")  # @break_into_debugger
        else:
            scratchpad["paused"] = False
            backchannel.send("loop?")
            assert backchannel.receive() == "proceed"
            while not scratchpad["paused"]:
                print("looping until paused")
                time.sleep(0.1)

    with debug.Session() as session:
        host, port = runners.attach_by_socket.host, runners.attach_by_socket.port
        session.config.update({"host": host, "port": port})

        backchannel = session.open_backchannel()
        session.spawn_debuggee(
            [code_to_debug, host, port, wait_for_attach, is_attached, stop_method]
        )
        session.wait_for_enable_attach()

        session.connect_to_adapter((host, port))
        with session.request_attach():
            pass

        if wait_for_attach:
            assert backchannel.receive() == "wait_for_attach"

        if is_attached:
            assert backchannel.receive() == "is_attached"

        if stop_method == "break_into_debugger":
            assert backchannel.receive() == "break_into_debugger?"
            backchannel.send("proceed")
            session.wait_for_stop(
                expected_frames=[some.dap.frame(code_to_debug, "break_into_debugger")]
            )
        elif stop_method == "pause":
            assert backchannel.receive() == "loop?"
            backchannel.send("proceed")
            session.request("pause", freeze=False)
            session.wait_for_stop("pause")
            session.scratchpad["paused"] = True
        else:
            pytest.fail(stop_method)

        session.request_continue()


@pytest.mark.parametrize("run", runners.all_attach)
@pytest.mark.skip(reason="https://github.com/microsoft/ptvsd/issues/1802")
def test_reattach(pyfile, target, run):
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

    with debug.Session() as session1:
        session1.captured_output = None
        session1.expected_exit_code = None  # not expected to exit on disconnect

        with run(session1, target(code_to_debug)):
            host, port = session1.config["host"], session1.config["port"]

        session1.wait_for_stop(expected_frames=[some.dap.frame(code_to_debug, "first")])
        session1.disconnect()

    with debug.Session() as session2:
        session2.config.update(session1.config)
        with session2.connect_to_adapter((host, port)):
            pass

        session2.wait_for_stop(
            expected_frames=[some.dap.frame(code_to_debug, "second")]
        )
        session2.scratchpad["exit"] = True


def test_attach_by_pid(pyfile, target):
    @pyfile
    def code_to_debug():
        import debug_me  # noqa
        import time

        def do_something(i):
            time.sleep(0.1)
            print(i)  # @bp

        for i in range(100):
            do_something(i)

    with debug.Session() as session:
        with session.attach_by_pid(target(code_to_debug), wait=False):
            session.set_breakpoints(code_to_debug, all)

        session.wait_for_stop(expected_frames=[some.dap.frame(code_to_debug, "bp")])

        # Remove breakpoint and continue.
        session.set_breakpoints(code_to_debug, [])
        session.request_continue()
        session.wait_for_next(
            Event("output", some.dict.containing({"category": "stdout"}))
        )
