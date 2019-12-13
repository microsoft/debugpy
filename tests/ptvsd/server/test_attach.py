# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, division, print_function, unicode_literals

import pytest

from tests import debug
from tests.debug import runners, targets
from tests.patterns import some


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


@pytest.mark.parametrize("run", runners.all_attach_by_socket)
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
        session1.captured_output = set()
        session1.expected_exit_code = None  # not expected to exit on disconnect

        with run(session1, target(code_to_debug)):
            pass

        session1.wait_for_stop(expected_frames=[some.dap.frame(code_to_debug, "first")])
        session1.disconnect()

    with debug.Session() as session2:
        session2.config.update(session1.config)
        if "host" in session2.config:
            session2.connect_to_adapter(
                (session2.config["host"], session2.config["port"])
            )

        with session2.request_attach():
            pass

        session2.wait_for_stop(
            expected_frames=[some.dap.frame(code_to_debug, "second")]
        )
        session2.scratchpad["exit"] = True
        session2.request_continue()


@pytest.mark.parametrize("pid_type", ["int", "str"])
def test_attach_by_pid(pyfile, target, pid_type):
    @pyfile
    def code_to_debug():
        import debug_me  # noqa
        import time

        def do_something(i):
            time.sleep(0.1)
            proceed = True
            print(i)  # @bp
            return proceed

        for i in range(100):
            if not do_something(i):
                break

    with debug.Session() as session:
        def before_request(command, arguments):
            if command == "attach":
                assert isinstance(arguments["processId"], int)
                if pid_type == "str":
                    arguments["processId"] = str(arguments["processId"])

        session.before_request = before_request
        session.config["redirectOutput"] = True

        with session.attach_by_pid(target(code_to_debug), wait=False):
            session.set_breakpoints(code_to_debug, all)

        stop = session.wait_for_stop(
            expected_frames=[some.dap.frame(code_to_debug, "bp")]
        )

        # Remove breakpoint and continue.
        session.request(
            "setExpression",
            {"frameId": stop.frame_id, "expression": "proceed", "value": "False"},
        )
        session.set_breakpoints(code_to_debug, [])
        session.request_continue()
        session.wait_for_next_event(
            "output", some.dict.containing({"category": "stdout"})
        )
