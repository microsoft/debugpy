# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import os.path
import pytest

from tests import debug
from tests.debug import start_methods
from tests.patterns import some


@pytest.mark.parametrize(
    "start_method", [start_methods.AttachSocketCmdLine, start_methods.AttachSocketImport]
)
def test_continue_on_disconnect_for_attach(pyfile, start_method, run_as):
    @pyfile
    def code_to_debug():
        from debug_me import backchannel

        backchannel.send("continued")  # @bp

    with debug.Session(start_method, backchannel=True) as session:
        backchannel = session.backchannel
        session.configure(run_as, code_to_debug)
        session.set_breakpoints(code_to_debug, all)
        session.start_debugging()

        session.wait_for_stop(
            "breakpoint",
            expected_frames=[
                some.dap.frame(code_to_debug, line="bp"),
            ],
        )
        session.request("disconnect")
        assert "continued" == backchannel.receive()


@pytest.mark.parametrize("start_method", [start_methods.Launch])
def test_exit_on_disconnect_for_launch(pyfile, start_method, run_as):
    @pyfile
    def code_to_debug():
        import debug_me  # noqa
        import os.path

        fp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "here.txt")  # @bp
        print("should not execute this")
        with open(fp, "w") as f:
            print("Should not continue after disconnect on launch", file=f)

    with debug.Session(start_method) as session:
        session.expected_exit_code = some.int
        session.configure(run_as, code_to_debug)
        session.set_breakpoints(code_to_debug, all)
        session.start_debugging()

        session.wait_for_stop(
            "breakpoint",
            expected_frames=[
                some.dap.frame(code_to_debug, line="bp"),
            ],
        )
        session.request("disconnect")

    fp = os.path.join(os.path.dirname(os.path.abspath(code_to_debug)), "here.txt")
    assert not os.path.exists(fp)
