# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import os
import sys
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
@pytest.mark.parametrize("expansion", ["preserve", "expand"])
@pytest.mark.parametrize("python_with_space", [False, True])
def test_shell_expansion(pyfile, tmpdir, target, run, expansion, python_with_space):
    if expansion == "expand" and run.console == "internalConsole":
        pytest.skip('Shell expansion is not supported for "internalConsole"')
    
    # Skip tests with python_with_space=True and target="code" on Windows
    # because .cmd wrappers cannot properly handle multiline string arguments
    if (python_with_space and target == targets.Code and sys.platform == "win32"):
        pytest.skip('Windows .cmd wrapper cannot handle multiline code arguments')

    @pyfile
    def code_to_debug():
        import sys
        import debuggee
        from debuggee import backchannel

        debuggee.setup()
        backchannel.send(sys.argv)

    def expand(args):
        if expansion != "expand":
            return
        log.info("Before expansion: {0}", args)
        for i, arg in enumerate(args):
            if arg.startswith("$"):
                args[i] = arg[1:]
        log.info("After expansion: {0}", args)

    captured_run_in_terminal_args = []
    
    class Session(debug.Session):
        def run_in_terminal(self, args, cwd, env):
            captured_run_in_terminal_args.append(args[:])  # Capture a copy of the args
            expand(args)
            return super().run_in_terminal(args, cwd, env)

    argslist = ["0", "$1", "2"]
    args = argslist if expansion == "preserve" else " ".join(argslist)
    
    with Session() as session:
        # Create a Python wrapper with a space in the path if requested
        if python_with_space:
            # Create a directory with a space in the name
            python_dir = tmpdir / "python with space"
            python_dir.mkdir()
            
            if sys.platform == "win32":
                wrapper = python_dir / "python.cmd"
                wrapper.write(f'@echo off\n"{sys.executable}" %*')
            else:
                wrapper = python_dir / "python.sh"
                wrapper.write(f'#!/bin/sh\nexec "{sys.executable}" "$@"')
                os.chmod(wrapper.strpath, 0o777)
            
            session.config["python"] = wrapper.strpath
        
        backchannel = session.open_backchannel()
        with run(session, target(code_to_debug, args=args)):
            pass

        argv = backchannel.receive()

    expand(argslist)
    assert argv == [some.str] + argslist

    # Verify that the python executable path is correctly quoted if it contains spaces
    if python_with_space and captured_run_in_terminal_args:
        terminal_args = captured_run_in_terminal_args[0]
        log.info("Captured runInTerminal args: {0}", terminal_args)
        
        # Check if the python executable (first arg) contains a space
        python_arg = terminal_args[0]
        assert "python with space" in python_arg, \
            f"Expected 'python with space' in python path: {python_arg}"
        if expansion == "expand":
            assert (python_arg.startswith('"') or python_arg.startswith("'")), f"Python_arg is not quoted: {python_arg}"
