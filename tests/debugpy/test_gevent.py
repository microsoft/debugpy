# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from tests import debug
from tests.patterns import some


def test_gevent(pyfile, target, run):
    @pyfile
    def code_to_debug():
        import os

        os.environ["GEVENT_SUPPORT"] = "True"

        from gevent import monkey

        monkey.patch_all()

        import threading
        from time import sleep

        # Note: importing ptvsd after the `monkey.patch_all` (with the GEVENT_SUPPORT
        # flag == 'True').
        import debuggee  # noqa

        debuggee.setup()

        called = []

        def myfunc():
            class MyGreenletThread(threading.Thread):
                def run(self):
                    print("break here", self.name)  # @bp
                    for _i in range(5):
                        called.append(self.name)  # break here
                        sleep()

            t1 = MyGreenletThread()
            t1.name = "t1"
            t2 = MyGreenletThread()
            t2.name = "t2"

            t1.start()
            t2.start()

            for t1 in (t1, t2):
                t1.join()

            # With gevent it's always the same (gevent coroutine support makes thread
            # switching serial).
            expected = ["t1", "t1", "t2", "t1", "t2", "t1", "t2", "t1", "t2", "t2"]
            if called != expected:
                raise AssertionError("Expected:\n%s\nFound:\n%s" % (expected, called))

        myfunc()

    with debug.Session() as session:
        session.config["gevent"] = True

        if str(run).startswith("attach"):
            session.spawn_debuggee.env["GEVENT_SUPPORT"] = "True"

        with run(session, target(code_to_debug)):
            session.set_breakpoints(code_to_debug, all)

        session.wait_for_stop(
            "breakpoint", expected_frames=[some.dap.frame(code_to_debug, "bp")]
        )
        session.request_continue()

        session.wait_for_stop(
            "breakpoint", expected_frames=[some.dap.frame(code_to_debug, "bp")]
        )

        session.request_continue()
