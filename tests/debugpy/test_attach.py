# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import pytest
import sys

from _pydevd_bundle.pydevd_constants import IS_PY312_OR_GREATER
from tests import debug
from tests.debug import runners
from tests.patterns import some


@pytest.mark.parametrize("stop_method", ["breakpoint", "pause"])
@pytest.mark.skipif(IS_PY312_OR_GREATER, reason="Flakey test on 312 and higher")
@pytest.mark.parametrize("is_client_connected", ["is_client_connected", ""])
@pytest.mark.parametrize("host", ["127.0.0.1", "::1"])
@pytest.mark.parametrize("wait_for_client", ["wait_for_client", pytest.param("", marks=pytest.mark.skipif(sys.platform.startswith("darwin"), reason="Flakey test on Mac"))])
def test_attach_api(pyfile, host, wait_for_client, is_client_connected, stop_method):
    @pyfile
    def code_to_debug():
        import debuggee
        import debugpy
        import sys
        import time
        from debuggee import backchannel, scratchpad

        # Test different ways of calling configure(). 
        debugpy.configure(qt="none", subProcess=True, python=sys.executable)
        debugpy.configure({"qt": "none", "subProcess": True, "python": sys.executable})
        debugpy.configure({"qt": "none"}, python=sys.executable)

        debuggee.setup()
        _, host, port, wait_for_client, is_client_connected, stop_method = sys.argv
        port = int(port)
        debugpy.listen(address=(host, port))

        if wait_for_client:
            backchannel.send("wait_for_client")
            debugpy.wait_for_client()

        if is_client_connected:
            backchannel.send("is_client_connected")
            while not debugpy.is_client_connected():
                print("looping until is_client_connected()")
                time.sleep(0.1)

        if stop_method == "breakpoint":
            backchannel.send("breakpoint?")
            assert backchannel.receive() == "proceed"
            debugpy.breakpoint()
            print("break")  # @breakpoint
        else:
            scratchpad["paused"] = False
            backchannel.send("loop?")
            assert backchannel.receive() == "proceed"
            while not scratchpad["paused"]:
                print("looping until paused")
                time.sleep(0.1)

    with debug.Session() as session:
        host = runners.attach_connect.host if host == "127.0.0.1" else host
        port = runners.attach_connect.port
        session.config.update({"connect": {"host": host, "port": port}})

        backchannel = session.open_backchannel()
        session.spawn_debuggee(
            [
                code_to_debug,
                host,
                port,
                wait_for_client,
                is_client_connected,
                stop_method,
            ]
        )
        session.wait_for_adapter_socket()

        session.expect_server_socket()
        session.connect_to_adapter((host, port))
        with session.request_attach():
            pass

        if wait_for_client:
            assert backchannel.receive() == "wait_for_client"

        if is_client_connected:
            assert backchannel.receive() == "is_client_connected"

        if stop_method == "breakpoint":
            assert backchannel.receive() == "breakpoint?"
            backchannel.send("proceed")
            session.wait_for_stop(
                expected_frames=[some.dap.frame(code_to_debug, "breakpoint")]
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

@pytest.mark.parametrize("host", ["127.0.0.1", "::1"])
def test_multiple_listen_raises_exception(pyfile, host):
    @pyfile
    def code_to_debug():
        import debuggee
        import debugpy
        import sys

        from debuggee import backchannel

        debuggee.setup()
        _, host, port = sys.argv
        port = int(port)
        debugpy.listen(address=(host, port))
        try:
            debugpy.listen(address=(host, port))
        except RuntimeError:
            backchannel.send("listen_exception")
        
        debugpy.wait_for_client()
        debugpy.breakpoint()
        print("break")  # @breakpoint

    host = runners.attach_connect.host if host == "127.0.0.1" else host
    port = runners.attach_connect.port
    with debug.Session() as session:
        backchannel = session.open_backchannel()
        session.spawn_debuggee(
            [
                code_to_debug,
                host,
                port,
            ]
        )
  
        session.wait_for_adapter_socket()
        session.expect_server_socket()
        session.connect_to_adapter((host, port))
        with session.request_attach():
            pass
        
        session.wait_for_stop(
            expected_frames=[some.dap.frame(code_to_debug, "breakpoint")]
        )
        assert backchannel.receive() == "listen_exception"
        session.request_continue()

@pytest.mark.parametrize("run", runners.all_attach_connect)
def test_reattach(pyfile, target, run):
    @pyfile
    def code_to_debug():
        import time
        import debuggee
        import debugpy
        from debuggee import scratchpad

        debuggee.setup()
        debugpy.breakpoint()
        object()  # @first

        scratchpad["exit"] = False
        while not scratchpad["exit"]:
            time.sleep(0.1)
            debugpy.breakpoint()
            object()  # @second

    with debug.Session() as session1:
        session1.captured_output = set()
        session1.expected_exit_code = None  # not expected to exit on disconnect

        with run(session1, target(code_to_debug)):
            expected_adapter_sockets = session1.expected_adapter_sockets.copy()

        session1.wait_for_stop(expected_frames=[some.dap.frame(code_to_debug, "first")])
        session1.disconnect()

    with debug.Session() as session2:
        session2.config.update(session1.config)
        session2.expected_adapter_sockets = expected_adapter_sockets
        if "connect" in session2.config:
            session2.connect_to_adapter(
                (session2.config["connect"]["host"], session2.config["connect"]["port"])
            )

        with session2.request_attach():
            pass

        session2.wait_for_stop(
            expected_frames=[some.dap.frame(code_to_debug, "second")]
        )
        session2.scratchpad["exit"] = True
        session2.request_continue()

    session1.wait_for_exit()


@pytest.mark.parametrize("pid_type", ["int", "str"])
@pytest.mark.skipif(
    not sys.platform.startswith("linux"),
    reason="https://github.com/microsoft/debugpy/issues/311",
)
@pytest.mark.flaky(retries=2, delay=1)
def test_attach_pid_client(pyfile, target, pid_type):
    @pyfile
    def code_to_debug():
        import debuggee
        import time

        debuggee.setup()

        def do_something(i):
            time.sleep(0.2)
            proceed = True
            print(i)  # @bp
            return proceed

        for i in range(500):
            if not do_something(i):
                break

    def before_request(command, arguments):
        if command == "attach":
            assert isinstance(arguments["processId"], int)
            if pid_type == "str":
                arguments["processId"] = str(arguments["processId"])

    session1 = debug.Session()

    session1.before_request = before_request
    session1.config["redirectOutput"] = True

    session1.captured_output = set()
    session1.expected_exit_code = None  # not expected to exit on disconnect

    with session1.attach_pid(target(code_to_debug), wait=False):
        session1.set_breakpoints(code_to_debug, all)

    session1.wait_for_stop(expected_frames=[some.dap.frame(code_to_debug, "bp")])

    pid = session1.config["processId"]

    # Note: don't call session1.disconnect because it'd deadlock in channel.close()
    # (because the fd is in a read() in a different thread, we can't call close() on it).
    session1.request("disconnect")
    session1.wait_for_terminated()

    with debug.Session() as session2:
        with session2.attach_pid(pid, wait=False):
            session2.set_breakpoints(code_to_debug, all)

        stop = session2.wait_for_stop(
            expected_frames=[some.dap.frame(code_to_debug, "bp")]
        )

        # Remove breakpoint and continue.
        session2.set_breakpoints(code_to_debug, [])
        session2.request(
            "setExpression",
            {"frameId": stop.frame_id, "expression": "proceed", "value": "False"},
        )
        session2.scratchpad["exit"] = True
        session2.request_continue()


@pytest.mark.parametrize("host", ["127.0.0.1", "::1"])
def test_cancel_wait(pyfile, host):
    @pyfile
    def code_to_debug():
        import debugpy
        import sys
        import threading
        import time

        from debuggee import backchannel

        def cancel():
            time.sleep(1)
            debugpy.wait_for_client.cancel()

        _, host, port = sys.argv
        port = int(port)
        debugpy.listen(address=(host, port))
        threading.Thread(target=cancel).start()
        debugpy.wait_for_client()
        backchannel.send("exit")

    with debug.Session() as session:
        host = runners.attach_connect.host if host == "127.0.0.1" else host
        port = runners.attach_connect.port
        session.config.update({"connect": {"host": host, "port": port}})
        session.expected_exit_code = None

        backchannel = session.open_backchannel()
        session.spawn_debuggee(
            [
                code_to_debug,
                host,
                port,
            ]
        )

        assert backchannel.receive() == "exit"
