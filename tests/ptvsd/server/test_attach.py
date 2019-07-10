# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import pytest

from tests import code, debug, test_data
from tests.patterns import some
from tests.timeline import Event


@pytest.mark.parametrize("wait_for_attach", ["waitOn", "waitOff"])
@pytest.mark.parametrize("is_attached", ["attachCheckOn", "attachCheckOff"])
@pytest.mark.parametrize("break_into", ["break", "pause"])
def test_attach(run_as, wait_for_attach, is_attached, break_into):
    attach1_py = test_data / "attach" / "attach1.py"
    lines = code.get_marked_line_numbers(attach1_py)
    with debug.Session() as session:
        env = {
            "PTVSD_TEST_HOST": "localhost",
            "PTVSD_TEST_PORT": str(session.ptvsd_port),
        }
        if wait_for_attach == "waitOn":
            env["PTVSD_WAIT_FOR_ATTACH"] = "1"
        if is_attached == "attachCheckOn":
            env["PTVSD_IS_ATTACHED"] = "1"
        if break_into == "break":
            env["PTVSD_BREAK_INTO_DBG"] = "1"

        backchannel = session.setup_backchannel()
        session.initialize(
            target=(run_as, attach1_py),
            start_method="launch",
            env=env,
        )
        session.start_debugging()

        if wait_for_attach == "waitOn":
            assert backchannel.receive() == "wait_for_attach"

        if is_attached == "attachCheckOn":
            assert backchannel.receive() == "is_attached"

        if break_into == "break":
            assert backchannel.receive() == "break_into_debugger"
            hit = session.wait_for_stop()
            assert lines["bp"] == hit.frames[0]["line"]
        else:
            # pause test
            backchannel.send("pause_test")
            session.send_request("pause").wait_for_response(freeze=False)
            hit = session.wait_for_stop(reason="pause")
            # Note: no longer asserting line as it can even stop on different files
            # (such as as backchannel.py).
            # assert hit.frames[0]['line'] in [27, 28, 29]

        session.request_continue()
        session.wait_for_exit()


@pytest.mark.parametrize(
    "start_method", ["attach_socket_cmdline", "attach_socket_import"]
)
def test_reattach(pyfile, start_method, run_as):
    @pyfile
    def code_to_debug():
        from debug_me import backchannel, ptvsd
        import time

        ptvsd.break_into_debugger()
        print("first") # @first
        backchannel.send("continued")
        for _ in range(0, 100):
            time.sleep(0.1)
            ptvsd.break_into_debugger()
            print("second") # @second

    with debug.Session() as session:
        backchannel = session.setup_backchannel()
        session.initialize(
            target=(run_as, code_to_debug),
            start_method=start_method,
            kill_ptvsd=False,
            capture_output=False,
        )
        session.start_debugging()
        hit = session.wait_for_stop()
        assert code_to_debug.lines["first"] == hit.frames[0]["line"]
        session.send_request("disconnect").wait_for_response(freeze=False)
        session.wait_for_disconnect()
        assert backchannel.receive() == "continued"

    with session.reattach(target=(run_as, code_to_debug)) as session2:
        session2.start_debugging()
        hit = session2.wait_for_stop()
        assert code_to_debug.lines["second"] == hit.frames[0]["line"]
        session2.send_request("disconnect").wait_for_response(freeze=False)
        session2.wait_for_disconnect()


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
            print(i)  # @break

        for i in range(100):
            do_something(i)

    with debug.Session() as session:
        session.initialize(target=(run_as, code_to_debug), start_method=start_method)
        session.set_breakpoints(code_to_debug, [code_to_debug.lines["break"]])
        session.start_debugging()
        hit = session.wait_for_stop()
        assert code_to_debug.lines["break"] == hit.frames[0]["line"]

        # remove breakpoint and continue
        session.set_breakpoints(code_to_debug, [])
        session.request_continue()
        session.wait_for_next(
            Event("output", some.dict.containing({"category": "stdout"}))
        )
        session.wait_for_exit()
