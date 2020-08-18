# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, division, print_function, unicode_literals

import pytest

from tests import debug
from tests.debug import runners


@pytest.mark.parametrize("run", runners.all)
@pytest.mark.parametrize("redirect_output", ["", "redirect_output"])
def test_stdin_not_patched(pyfile, target, run, redirect_output):
    @pyfile
    def code_to_debug():
        import sys
        import debuggee
        from debuggee import backchannel

        debuggee.setup()
        backchannel.send(sys.stdin is sys.__stdin__)

    with debug.Session() as session:
        session.config["redirectOutput"] = bool(redirect_output)

        backchannel = session.open_backchannel()
        with run(session, target(code_to_debug)):
            pass

        is_original_stdin = backchannel.receive()
        assert is_original_stdin, "Expected sys.stdin and sys.__stdin__ to be the same."


@pytest.mark.parametrize("run", runners.all_launch_terminal + runners.all_attach)
@pytest.mark.parametrize("redirect_output", ["", "redirect_output"])
def test_input(pyfile, target, run, redirect_output):
    @pyfile
    def code_to_debug():
        import debuggee
        from debuggee import backchannel

        try:
            input = raw_input
        except NameError:
            pass

        debuggee.setup()
        backchannel.send(input())

    with debug.Session() as session:
        session.config["redirectOutput"] = bool(redirect_output)

        backchannel = session.open_backchannel()
        with run(session, target(code_to_debug)):
            pass

        session.debuggee.stdin.write(b"ok\n")
        s = backchannel.receive()
        assert s == "ok"
