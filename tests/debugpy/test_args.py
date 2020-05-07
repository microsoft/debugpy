# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, division, print_function, unicode_literals

import pytest

from debugpy.common import log
from tests import debug
from tests.debug import runners, targets
from tests.patterns import some


@pytest.mark.parametrize("target", targets.all)
@pytest.mark.parametrize("run", runners.all)
def test_args(pyfile, target, run):
    @pyfile
    def code_to_debug():
        import sys
        import debuggee
        from debuggee import backchannel

        debuggee.setup()
        backchannel.send(sys.argv)

    args = ["--arg1", "arg2", "-arg3", "--", "arg4", "-a"]

    with debug.Session() as session:
        backchannel = session.open_backchannel()
        with run(session, target(code_to_debug, args=args)):
            pass
        argv = backchannel.receive()
        assert argv == [some.str] + args


@pytest.mark.parametrize("target", targets.all)
@pytest.mark.parametrize("run", runners.all_launch)
@pytest.mark.parametrize("expansion", ["", "none", "shell"])
def test_shell_expansion(pyfile, target, run, expansion):
    @pyfile
    def code_to_debug():
        import sys
        import debuggee
        from debuggee import backchannel

        debuggee.setup()
        backchannel.send(sys.argv)

    def expand(args):
        log.info("Before expansion: {0}", args)
        for i, arg in enumerate(args):
            if arg.startswith("$"):
                args[i] = arg[1:]
        log.info("After expansion: {0}", args)

    class Session(debug.Session):
        def run_in_terminal(self, args, cwd, env):
            expand(args)
            return super(Session, self).run_in_terminal(args, cwd, env)

    args = ["0", "$1", "2"]
    with Session() as session:
        if expansion:
            session.config["argsExpansion"] = expansion

        backchannel = session.open_backchannel()
        with run(session, target(code_to_debug, args=args)):
            pass

        argv = backchannel.receive()

    if session.config["console"] != "internalConsole" and expansion != "none":
        expand(args)
    assert argv == [some.str] + args
