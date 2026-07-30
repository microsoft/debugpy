# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import os
import subprocess
import sys

import pytest

from tests import debug


def test_cli_options_with_no_debugger():
    import debugpy

    cli_options = debugpy.get_cli_options()
    assert cli_options is None


def test_cli_options_under_file_connect(pyfile, target, run):
    @pyfile
    def code_to_debug():
        import dataclasses
        import debugpy

        import debuggee
        from debuggee import backchannel

        debuggee.setup()
        backchannel.send(dataclasses.asdict(debugpy.get_cli_options()))

    with debug.Session() as session:
        backchannel = session.open_backchannel()

        with run(session, target(code_to_debug)):
            pass

        cli_options = backchannel.receive()
        assert cli_options['mode'] == 'connect'
        assert cli_options['target_kind'] == 'file'


@pytest.mark.parametrize("target_kind", ["file", "module", "code"])
@pytest.mark.parametrize("python_flag", ["-I", "-P"])
def test_safe_sys_path_modes(pyfile, tmpdir, target_kind, python_flag):
    # In isolated mode (-I) and safe-path mode (-P / PYTHONSAFEPATH), Python does
    # not prepend the script directory (for a file target) or the current directory
    # (for -m and -c) to sys.path, and neither should debugpy.
    # https://github.com/microsoft/debugpy/issues/1916
    if python_flag == "-P" and sys.version_info < (3, 11):
        pytest.skip("-P / PYTHONSAFEPATH requires Python 3.11+")

    import debugpy

    @pyfile
    def code_to_debug():
        import sys

        print(repr(sys.path[0]))

    debugpy_root = os.path.dirname(os.path.dirname(os.path.abspath(debugpy.__file__)))

    code = "import sys; print(repr(sys.path[0]))"
    cli_args = ["--listen", "127.0.0.1:0"]
    if target_kind == "file":
        cli_args += [code_to_debug.strpath]
        not_expected = os.path.dirname(code_to_debug.strpath)
    elif target_kind == "module":
        tmpdir.join("debuggee_module.py").write(code)
        cli_args += ["-m", "debuggee_module"]
        not_expected = ""
    else:
        cli_args += ["-c", code]
        not_expected = ""

    # -I / -P do not block explicit sys.path edits, so make debugpy (and the module
    # target) importable by inserting their locations before invoking the CLI, the
    # same way they would be resolved from site-packages of an installed copy.
    wrapper = (
        "import sys; "
        "sys.path.insert(0, {tmpdir!r}); "
        "sys.path.insert(0, {debugpy_root!r}); "
        "sys.argv[1:] = {cli_args!r}; "
        "from debugpy.server import cli; cli.main()".format(
            tmpdir=tmpdir.strpath, debugpy_root=debugpy_root, cli_args=cli_args
        )
    )

    output = subprocess.check_output(
        [sys.executable, python_flag, "-c", wrapper],
        cwd=tmpdir.strpath,
        stderr=subprocess.DEVNULL,
    )

    sys_path_0 = output.decode("utf-8").strip().splitlines()[-1]
    assert sys_path_0 != repr(not_expected)
