# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

"""Tests for the injector selection logic in pydevd's add_code_to_python_process.

These cover the Linux gdb/lldb dispatcher and the lldb command line that it builds.
Neither gdb nor lldb is actually spawned, so they run on any platform.
"""

import importlib.util
import os
import pytest

from unittest import mock

import debugpy


ATTACH_TO_PROCESS_DIR = os.path.join(
    os.path.dirname(os.path.abspath(debugpy.__file__)),
    "_vendored",
    "pydevd",
    "pydevd_attach_to_process",
)


@pytest.fixture(scope="module")
def acpp():
    """add_code_to_python_process, loaded by path.

    The module is not part of any package - debugpy itself imports it by appending
    pydevd_attach_to_process to sys.path - so it is loaded here under a private name
    to avoid clashing with that import.
    """
    path = os.path.join(ATTACH_TO_PROCESS_DIR, "add_code_to_python_process.py")
    spec = importlib.util.spec_from_file_location(
        "add_code_to_python_process_under_test", path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def injectors(acpp):
    """Replaces both leaf injectors with mocks, and yields them as (gdb, lldb)."""
    with mock.patch.object(acpp, "run_python_code_linux_gdb") as gdb:
        with mock.patch.object(acpp, "run_python_code_linux_lldb") as lldb:
            yield gdb, lldb


# gdb is the default; lldb is opt-in via PYDEVD_ATTACH_PREFER_LLDB, and only if it is
# actually on the PATH.
@pytest.mark.parametrize(
    "env_value, lldb_on_path, expect_lldb",
    [
        (None, "/usr/bin/lldb", False),
        ("", "/usr/bin/lldb", False),
        ("0", "/usr/bin/lldb", False),
        ("no", "/usr/bin/lldb", False),
        ("1", "/usr/bin/lldb", True),
        (" 1 ", "/usr/bin/lldb", True),
        ("true", "/usr/bin/lldb", True),
        ("TRUE", "/usr/bin/lldb", True),
        ("yes", "/usr/bin/lldb", True),
        ("Yes", "/usr/bin/lldb", True),
        # Preferred, but not installed - must transparently fall back to gdb.
        ("1", None, False),
        ("true", None, False),
    ],
)
def test_run_python_code_linux_dispatch(
    acpp, injectors, env_value, lldb_on_path, expect_lldb
):
    gdb, lldb = injectors

    with mock.patch.dict(os.environ, clear=False) as env:
        env.pop("PYDEVD_ATTACH_PREFER_LLDB", None)
        if env_value is not None:
            env["PYDEVD_ATTACH_PREFER_LLDB"] = env_value

        with mock.patch.object(acpp.shutil, "which", return_value=lldb_on_path):
            acpp.run_python_code_linux(
                123, "print(1)", connect_debugger_tracing=True, show_debug_info=0
            )

    expected_call = mock.call(123, "print(1)", True, 0)
    if expect_lldb:
        assert lldb.mock_calls == [expected_call]
        assert gdb.mock_calls == []
    else:
        assert gdb.mock_calls == [expected_call]
        assert lldb.mock_calls == []


def test_run_python_code_linux_is_the_dispatcher(acpp):
    """The Linux entry point must be the dispatcher, not gdb directly - otherwise the
    preference is read at import time and never takes effect."""
    if acpp.IS_LINUX:
        assert acpp.run_python_code is acpp.run_python_code_linux
    assert acpp.run_python_code_linux is not acpp.run_python_code_linux_gdb


def test_run_python_code_linux_lldb_command(acpp):
    target_dll = "/some/where/attach_linux_amd64.so"
    lldb_prepare = os.path.normpath(
        os.path.join(ATTACH_TO_PROCESS_DIR, "linux_and_mac", "lldb_prepare.py")
    )
    assert os.path.exists(lldb_prepare)

    with mock.patch.object(acpp, "get_target_filename", return_value=target_dll):
        with mock.patch.object(acpp.subprocess, "check_call") as check_call:
            acpp.run_python_code_linux_lldb(
                4242, "print(1)", connect_debugger_tracing=True, show_debug_info=0
            )

    check_call.assert_called_once()
    (cmd,), kwargs = check_call.call_args
    assert kwargs["shell"]

    assert cmd.startswith("lldb --no-lldbinit --script-language Python ")
    assert "-o 'process attach --pid 4242'" in cmd
    assert "-o 'command script import \"%s\"'" % (lldb_prepare,) in cmd
    assert '-o \'load_lib_and_attach "%s" 0 "print(1)" 0\'' % (target_dll,) in cmd
    assert "-o 'process detach'" in cmd
    assert "-o 'script import os; os._exit(0)'" in cmd

    # lldb may have a builtin Python of a different version, so these must not leak in.
    env = kwargs["env"]
    assert "PYTHONPATH" not in env
    assert "PYTHONIOENCODING" not in env


def test_run_python_code_linux_lldb_rejects_single_quotes(acpp):
    with pytest.raises(AssertionError):
        acpp.run_python_code_linux_lldb(4242, "print('hi')")


def test_run_python_code_linux_lldb_requires_target_dll(acpp):
    with mock.patch.object(acpp, "get_target_filename", return_value=None):
        with pytest.raises(RuntimeError) as ex:
            acpp.run_python_code_linux_lldb(4242, "print(1)")

    assert "Could not find .so" in str(ex.value)
