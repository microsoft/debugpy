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
import sys
from contextlib import nullcontext
from types import SimpleNamespace

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
    assert spec is not None and spec.loader is not None
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


def test_lldb_command(acpp):
    target_dll = "/some/where/attach_linux_amd64.so"
    lldb_prepare = os.path.normpath(
        os.path.join(ATTACH_TO_PROCESS_DIR, "linux_and_mac", "lldb_prepare.py")
    )
    assert os.path.exists(lldb_prepare)

    with mock.patch.object(acpp, "get_target_filename", return_value=target_dll):
        with mock.patch.object(acpp.subprocess, "check_call") as check_call:
            acpp._run_python_code_lldb(4242, "print(1)", "not found", show_debug_info=7)

    check_call.assert_called_once()
    (cmd,), kwargs = check_call.call_args
    assert kwargs["shell"]

    assert cmd.startswith("lldb --no-lldbinit --script-language Python ")
    assert "-o 'process attach --pid 4242'" in cmd
    assert "-o 'command script import \"%s\"'" % (lldb_prepare,) in cmd
    assert '-o \'load_lib_and_attach "%s" 0 "print(1)" 7\'' % (target_dll,) in cmd
    assert "-o 'process detach'" in cmd
    assert "-o 'script import os; os._exit(0)'" in cmd

    # lldb may have a builtin Python of a different version, so these must not leak in.
    env = kwargs["env"]
    assert "PYTHONPATH" not in env
    assert "PYTHONIOENCODING" not in env


def test_lldb_rejects_single_quotes(acpp):
    with pytest.raises(AssertionError):
        acpp._run_python_code_lldb(4242, "print('hi')", "not found")


def test_lldb_requires_target_dll(acpp):
    with mock.patch.object(acpp, "get_target_filename", return_value=None):
        with pytest.raises(RuntimeError) as ex:
            acpp._run_python_code_lldb(4242, "print(1)", "Could not find .xyz")

    assert "Could not find .xyz" in str(ex.value)


# The platform wrappers add nothing but the library-not-found message, so that - and
# correct forwarding of the remaining arguments - is all they are tested for.
@pytest.mark.parametrize(
    "injector_name, expected_error",
    [
        ("run_python_code_linux_lldb", "Could not find .so for attach to process."),
        ("run_python_code_mac", "Could not find .dylib for attach to process."),
    ],
)
def test_lldb_wrapper_delegates(acpp, injector_name, expected_error):
    with mock.patch.object(acpp, "_run_python_code_lldb") as helper:
        getattr(acpp, injector_name)(
            4242, "print(1)", connect_debugger_tracing=True, show_debug_info=7
        )

    helper.assert_called_once_with(4242, "print(1)", expected_error, 7)


@pytest.mark.parametrize("target_arch", ["x86", "amd64", "arm64"])
@pytest.mark.parametrize(
    "prefix, extension",
    [("attach_", ".dll"), ("inject_dll_", ".exe"), ("run_code_on_dllmain_", ".dll")],
)
def test_windows_target_filename(acpp, monkeypatch, target_arch, prefix, extension):
    monkeypatch.setattr(acpp, "IS_WINDOWS", True)
    monkeypatch.setenv("PROCESSOR_ARCHITECTURE", "ARM64")
    monkeypatch.setenv("PROCESSOR_ARCHITEW6432", "ARM64")
    with mock.patch.object(acpp.os.path, "exists", return_value=True):
        filename = acpp.get_target_filename(
            prefix=prefix, extension=extension, target_arch=target_arch
        )
    assert os.path.basename(filename) == f"{prefix}{target_arch}{extension}"


@pytest.mark.parametrize("bits, suffix", [(False, "x86"), (True, "amd64")])
def test_windows_legacy_bitness_filename(acpp, monkeypatch, bits, suffix):
    monkeypatch.setattr(acpp, "IS_WINDOWS", True)
    with mock.patch.object(acpp.os.path, "exists", return_value=True):
        assert (
            os.path.basename(acpp.get_target_filename(bits)) == f"attach_{suffix}.dll"
        )


def test_windows_target_filename_missing_or_unsupported(acpp, monkeypatch):
    monkeypatch.setattr(acpp, "IS_WINDOWS", True)
    with mock.patch.object(acpp.os.path, "exists", return_value=False):
        assert acpp.get_target_filename(target_arch="arm64") is None
    with pytest.raises(RuntimeError, match="Unsupported Windows target"):
        acpp.get_target_filename(target_arch="arm64ec")
    with pytest.raises(AssertionError, match="target architecture"):
        acpp.get_target_filename()


@pytest.fixture
def windows_kernel(acpp, monkeypatch):
    kernel = SimpleNamespace(
        OpenProcess=mock.Mock(return_value=0x123456789),
        CloseHandle=mock.Mock(return_value=True),
        IsWow64Process2=mock.Mock(),
    )
    monkeypatch.setattr(acpp.ctypes, "WinDLL", lambda *a, **kw: kernel, raising=False)
    monkeypatch.setattr(
        acpp.ctypes,
        "WinError",
        lambda code: OSError(code, "Windows API failure"),
        raising=False,
    )
    monkeypatch.setattr(acpp.ctypes, "get_last_error", lambda: 5, raising=False)
    return kernel


@pytest.mark.parametrize(
    "process_machine, native_machine, expected",
    [
        (0, 0xAA64, "arm64"),
        (0x8664, 0xAA64, "amd64"),
        (0x014C, 0xAA64, "x86"),
        (0, 0x8664, "amd64"),
        (0x014C, 0x8664, "x86"),
        (0, 0x014C, "x86"),
    ],
)
def test_windows_process_architecture(
    acpp, windows_kernel, process_machine, native_machine, expected
):
    def query(handle, process, native):
        assert handle == 0x123456789
        process._obj.value = process_machine
        native._obj.value = native_machine
        return True

    windows_kernel.IsWow64Process2.side_effect = query
    assert acpp.get_windows_process_architecture(4242) == expected
    windows_kernel.OpenProcess.assert_called_once_with(0x1000, False, 4242)
    windows_kernel.CloseHandle.assert_called_once_with(0x123456789)
    assert windows_kernel.OpenProcess.restype is acpp.wintypes.HANDLE


@pytest.mark.parametrize("failure", ["open", "query", "machine", "close"])
def test_windows_process_architecture_errors(acpp, windows_kernel, failure):
    def query(handle, process, native):
        native._obj.value = 0xAA64
        return True

    windows_kernel.IsWow64Process2.side_effect = query
    if failure == "open":
        windows_kernel.OpenProcess.return_value = 0
    elif failure == "query":
        windows_kernel.IsWow64Process2.side_effect = None
        windows_kernel.IsWow64Process2.return_value = False
    elif failure == "machine":

        def query(handle, process, native):
            process._obj.value = 0xA641  # ARM64EC is not an ARM64 target.
            native._obj.value = 0xAA64
            return True

        windows_kernel.IsWow64Process2.side_effect = query
    else:
        windows_kernel.CloseHandle.return_value = False
    expected = RuntimeError if failure == "machine" else OSError
    with pytest.raises(expected):
        acpp.get_windows_process_architecture(4242)
    if failure == "open":
        windows_kernel.CloseHandle.assert_not_called()
    else:
        windows_kernel.CloseHandle.assert_called_once()


@pytest.mark.parametrize("bits, expected", [(32, "x86"), (64, "amd64")])
def test_windows_process_architecture_legacy(
    acpp, windows_kernel, monkeypatch, bits, expected
):
    del windows_kernel.IsWow64Process2
    process = mock.Mock()
    process.get_bits.return_value = bits
    win32 = SimpleNamespace(arch="amd64", ARCH_I386="i386", ARCH_AMD64="amd64")
    monkeypatch.setitem(sys.modules, "winappdbg", SimpleNamespace(win32=win32))
    monkeypatch.setitem(
        sys.modules, "winappdbg.process", SimpleNamespace(Process=lambda pid: process)
    )
    assert acpp.get_windows_process_architecture(4242) == expected
    windows_kernel.OpenProcess.assert_not_called()


def test_windows_legacy_api_rejects_unknown_native_architecture(
    acpp, windows_kernel, monkeypatch
):
    del windows_kernel.IsWow64Process2
    win32 = SimpleNamespace(arch="arm64", ARCH_I386="i386", ARCH_AMD64="amd64")
    monkeypatch.setitem(sys.modules, "winappdbg", SimpleNamespace(win32=win32))
    monkeypatch.setitem(
        sys.modules, "winappdbg.process", SimpleNamespace(Process=mock.Mock())
    )
    with pytest.raises(RuntimeError, match="IsWow64Process2 is required"):
        acpp.get_windows_process_architecture(4242)


@pytest.mark.parametrize("target_arch", ["x86", "amd64", "arm64"])
@pytest.mark.parametrize("completed", [True, False])
def test_windows_injection_uses_target_architecture(
    acpp, monkeypatch, target_arch, completed
):
    monkeypatch.setattr(acpp, "IS_WINDOWS", True)
    monkeypatch.setattr(
        acpp, "get_windows_process_architecture", lambda pid: target_arch
    )
    monkeypatch.setattr(acpp, "_acquire_mutex", lambda *a: nullcontext())
    monkeypatch.setattr(
        acpp, "_win_write_to_shared_named_memory", lambda *a: nullcontext()
    )
    event = mock.Mock()
    event.wait_for_event_set.return_value = completed
    monkeypatch.setattr(acpp, "_create_win_event", lambda *a: nullcontext(event))
    with mock.patch.object(acpp.os.path, "exists", return_value=True):
        with mock.patch.object(acpp.subprocess, "check_call") as check_call:
            if completed:
                acpp.run_python_code_windows(4242, "print(1)")
            else:
                with pytest.raises(acpp.TimeoutError, match="Timed out"):
                    acpp.run_python_code_windows(4242, "print(1)")
    assert [
        [os.path.basename(arg) for arg in call.args[0]]
        for call in check_call.call_args_list
    ] == [
        [f"inject_dll_{target_arch}.exe", "4242", f"attach_{target_arch}.dll"],
        [
            f"inject_dll_{target_arch}.exe",
            "4242",
            f"run_code_on_dllmain_{target_arch}.dll",
        ],
    ]
