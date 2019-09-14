# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import os.path
import pytest

from tests import debug
from tests.debug import runners
from tests.patterns import some


@pytest.mark.parametrize(
    "run", [runners.attach_by_socket["api"], runners.attach_by_socket["cli"]]
)
def test_continue_on_disconnect_for_attach(pyfile, target, run):
    @pyfile
    def code_to_debug():
        from debug_me import backchannel

        backchannel.send("continued")  # @bp

    with debug.Session() as session:
        backchannel = session.open_backchannel()
        with run(session, target(code_to_debug)):
            session.set_breakpoints(code_to_debug, all)

        session.wait_for_stop(
            "breakpoint", expected_frames=[some.dap.frame(code_to_debug, line="bp")]
        )
        session.disconnect()
        assert "continued" == backchannel.receive()


@pytest.mark.parametrize("run", runners.all_launch)
def test_exit_on_disconnect_for_launch(pyfile, target, run):
    @pyfile
    def code_to_debug():
        import debug_me  # noqa
        import os.path

        fp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "here.txt")  # @bp
        print("should not execute this")
        with open(fp, "w") as f:
            print("Should not continue after disconnect on launch", file=f)

    with debug.Session() as session:
        session.expected_exit_code = some.int
        with run(session, target(code_to_debug)):
            session.set_breakpoints(code_to_debug, all)

        session.wait_for_stop(
            "breakpoint", expected_frames=[some.dap.frame(code_to_debug, line="bp")]
        )
        session.disconnect()

    fp = os.path.join(os.path.dirname(os.path.abspath(code_to_debug)), "here.txt")
    assert not os.path.exists(fp)
