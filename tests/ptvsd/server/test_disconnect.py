# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import os.path
import pytest

from tests import debug
from tests.patterns import some
from tests.timeline import Event


@pytest.mark.parametrize(
    "start_method", ["attach_socket_cmdline", "attach_socket_import"]
)
def test_continue_on_disconnect_for_attach(pyfile, start_method, run_as):
    @pyfile
    def code_to_debug():
        from debug_me import backchannel

        backchannel.send("continued")  # @bp

    with debug.Session() as session:
        backchannel = session.setup_backchannel()
        session.initialize(
            target=(run_as, code_to_debug),
            start_method=start_method,
            ignore_unobserved=[Event("exited"), Event("terminated")],
        )
        session.set_breakpoints(code_to_debug, [code_to_debug.lines["bp"]])
        session.start_debugging()
        hit = session.wait_for_stop("breakpoint")
        assert hit.frames[0]["line"] == code_to_debug.lines["bp"]
        session.send_request("disconnect").wait_for_response()
        session.wait_for_disconnect()
        assert "continued" == backchannel.receive()


@pytest.mark.parametrize("start_method", ["launch"])
@pytest.mark.skip(reason="Bug #1052")
def test_exit_on_disconnect_for_launch(pyfile, start_method, run_as):
    @pyfile
    def code_to_debug():
        import debug_me  # noqa
        import os.path

        fp = os.join(os.path.dirname(os.path.abspath(__file__)), "here.txt")  # @bp
        # should not execute this
        with open(fp, "w") as f:
            print("Should not continue after disconnect on launch", file=f)

    with debug.Session() as session:
        session.initialize(
            target=(run_as, code_to_debug),
            start_method=start_method,
            expected_returncode=some.int,
        )
        session.set_breakpoints(code_to_debug, code_to_debug.lines["bp"])
        session.start_debugging()
        hit = session.wait_for_stop("breakpoint")
        assert hit.frames[0]["line"] == code_to_debug.lines["bp"]
        session.send_request("disconnect").wait_for_response()
        session.wait_for_exit()
        fp = os.join(os.path.dirname(os.path.abspath(code_to_debug)), "here.txt")
        assert not os.path.exists(fp)
