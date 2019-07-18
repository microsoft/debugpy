from debug_me import backchannel, ptvsd, scratchpad

import os
import time

ptvsd.enable_attach(("localhost", int(os.environ["ATTACH1_TEST_PORT"])))

if int(os.environ["ATTACH1_WAIT_FOR_ATTACH"]):
    backchannel.send("wait_for_attach")
    ptvsd.wait_for_attach()

if int(os.environ["ATTACH1_IS_ATTACHED"]):
    backchannel.send("is_attached")
    while not ptvsd.is_attached():
        print("looping until is_attached")
        time.sleep(0.1)

if int(os.environ["ATTACH1_BREAK_INTO_DEBUGGER"]):
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
