# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, division, print_function, unicode_literals

import os
import pytest

from tests import debug
from tests.debug import runners
from tests.patterns import some


@pytest.mark.parametrize("run", runners.all_attach_socket)
def test_continue_on_disconnect_for_attach(pyfile, target, run):
    @pyfile
    def code_to_debug():
        import debuggee
        from debuggee import backchannel

        debuggee.setup()
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
        import debuggee
        import sys

        debuggee.setup()
        filename = sys.argv[1]  # @bp
        # Disconnect happens here; subsequent lines should not run.
        with open(filename, "w") as f:
            f.write("failed")

    filename = (code_to_debug.dirpath() / "failed.txt").strpath

    with debug.Session() as session:
        session.expected_exit_code = some.int
        with run(session, target(code_to_debug, args=[filename])):
            session.set_breakpoints(code_to_debug, all)

        session.wait_for_stop(
            "breakpoint", expected_frames=[some.dap.frame(code_to_debug, line="bp")]
        )
        session.disconnect()

    assert not os.path.exists(filename)
