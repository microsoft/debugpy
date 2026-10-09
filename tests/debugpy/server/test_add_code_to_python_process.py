# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

"""Tests for the injectors and Windows IPC in pydevd's add_code_to_python_process.

Native APIs and subprocesses are mocked so these run on any platform.
"""

import importlib.util
import os
import pytest
import sys
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
    memory = acpp.ctypes.create_string_buffer(2048)
    kernel = SimpleNamespace(
        OpenProcess=mock.Mock(return_value=0x123456789),
        CloseHandle=mock.Mock(return_value=True),
        IsWow64Process2=mock.Mock(),
        CreateMutexW=mock.Mock(return_value=0x12345678A),
        ReleaseMutex=mock.Mock(return_value=True),
        WaitForSingleObject=mock.Mock(return_value=0),
        CreateEventW=mock.Mock(return_value=0x12345678C),
        CreateFileMappingW=mock.Mock(return_value=0x12345678B),
        MapViewOfFile=mock.Mock(return_value=acpp.ctypes.addressof(memory)),
        UnmapViewOfFile=mock.Mock(return_value=True),
        memory=memory,
    )
    monkeypatch.setattr(
        acpp.ctypes, "WinDLL", mock.Mock(return_value=kernel), raising=False
    )
    monkeypatch.setattr(
        acpp.ctypes,
        "WinError",
        lambda code: OSError(code, "Windows API failure"),
        raising=False,
    )
    monkeypatch.setattr(acpp.ctypes, "get_last_error", lambda: 5, raising=False)
    return kernel


def test_windows_kernel32_signatures(acpp, windows_kernel):
    ctypes = acpp.ctypes
    wintypes = acpp.wintypes
    signatures = {
        "OpenProcess": ([wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
        "CloseHandle": ([wintypes.HANDLE], wintypes.BOOL),
        "CreateMutexW": (
            [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR],
            wintypes.HANDLE,
        ),
        "ReleaseMutex": ([wintypes.HANDLE], wintypes.BOOL),
        "WaitForSingleObject": ([wintypes.HANDLE, wintypes.DWORD], wintypes.DWORD),
        "CreateEventW": (
            [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR],
            wintypes.HANDLE,
        ),
        "CreateFileMappingW": (
            [
                wintypes.HANDLE,
                ctypes.c_void_p,
                wintypes.DWORD,
                wintypes.DWORD,
                wintypes.DWORD,
                wintypes.LPCWSTR,
            ],
            wintypes.HANDLE,
        ),
        "MapViewOfFile": (
            [
                wintypes.HANDLE,
                wintypes.DWORD,
                wintypes.DWORD,
                wintypes.DWORD,
                ctypes.c_size_t,
            ],
            ctypes.c_void_p,
        ),
        "UnmapViewOfFile": ([ctypes.c_void_p], wintypes.BOOL),
    }
    assert acpp._get_windows_kernel32() is windows_kernel
    acpp.ctypes.WinDLL.assert_called_once_with("kernel32", use_last_error=True)
    for name, (args, result) in signatures.items():
        function = getattr(windows_kernel, name)
        assert function.argtypes == args
        assert function.restype is result


@pytest.mark.parametrize("result", [0, 0x80])
def test_windows_mutex_ownership(acpp, windows_kernel, result):
    windows_kernel.WaitForSingleObject.return_value = result
    operations = mock.Mock()
    operations.attach_mock(windows_kernel.ReleaseMutex, "release")
    operations.attach_mock(windows_kernel.CloseHandle, "close")
    with acpp._acquire_mutex("_pydevd_pid_attach_mutex_4242", 10):
        windows_kernel.CreateMutexW.assert_called_once_with(
            None, False, "_pydevd_pid_attach_mutex_4242"
        )
        windows_kernel.WaitForSingleObject.assert_called_once_with(0x12345678A, 10000)
        assert operations.mock_calls == []
    assert operations.mock_calls == [
        mock.call.release(0x12345678A),
        mock.call.close(0x12345678A),
    ]


@pytest.mark.parametrize("failure", ["create", "timeout", "wait", "release", "close"])
def test_windows_mutex_errors(acpp, windows_kernel, failure):
    if failure == "create":
        windows_kernel.CreateMutexW.return_value = None
    elif failure == "timeout":
        windows_kernel.WaitForSingleObject.return_value = 0x102
    elif failure == "wait":
        windows_kernel.WaitForSingleObject.return_value = 0xFFFFFFFF
    elif failure == "release":
        windows_kernel.ReleaseMutex.return_value = False
    else:
        windows_kernel.CloseHandle.return_value = False
    expected = acpp.TimeoutError if failure == "timeout" else OSError
    with pytest.raises(expected) as exc:
        with acpp._acquire_mutex("mutex", 10):
            assert failure in ("release", "close")
    if failure != "timeout":
        assert exc.value.errno == 5
    if failure == "create":
        windows_kernel.WaitForSingleObject.assert_not_called()
        windows_kernel.CloseHandle.assert_not_called()
    else:
        windows_kernel.CloseHandle.assert_called_once_with(0x12345678A)
    if failure in ("create", "timeout", "wait"):
        windows_kernel.ReleaseMutex.assert_not_called()
    else:
        windows_kernel.ReleaseMutex.assert_called_once_with(0x12345678A)


@pytest.mark.parametrize("name", ["event", b"event"])
@pytest.mark.parametrize("timeout, milliseconds", [(None, 0xFFFFFFFF), (1.25, 1250)])
@pytest.mark.parametrize("result, signaled", [(0, True), (0x80, True), (0x102, False)])
def test_windows_event_wait(
    acpp, windows_kernel, name, timeout, milliseconds, result, signaled
):
    windows_kernel.WaitForSingleObject.return_value = result
    with acpp._create_win_event(name) as event:
        assert event.wait_for_event_set(timeout) is signaled
        windows_kernel.CloseHandle.assert_not_called()
    windows_kernel.CreateEventW.assert_called_once_with(None, False, False, "event")
    windows_kernel.WaitForSingleObject.assert_called_once_with(0x12345678C, milliseconds)
    windows_kernel.CloseHandle.assert_called_once_with(0x12345678C)


@pytest.mark.parametrize("failure", ["create", "wait", "close"])
def test_windows_event_errors(acpp, windows_kernel, failure):
    if failure == "create":
        windows_kernel.CreateEventW.return_value = None
    elif failure == "wait":
        windows_kernel.WaitForSingleObject.return_value = 0xFFFFFFFF
    else:
        windows_kernel.CloseHandle.return_value = False
    with pytest.raises(OSError) as exc:
        with acpp._create_win_event("event") as event:
            event.wait_for_event_set(15)
    assert exc.value.errno == 5
    if failure == "create":
        windows_kernel.WaitForSingleObject.assert_not_called()
        windows_kernel.CloseHandle.assert_not_called()
    else:
        windows_kernel.CloseHandle.assert_called_once_with(0x12345678C)


@pytest.mark.parametrize(
    "payload",
    [b"print(1)", 'print("\u00e9")'.encode("utf-8"), b"x" * 2046],
    ids=["ascii", "utf8", "maximum-size"],
)
def test_windows_shared_memory_payload(acpp, windows_kernel, payload):
    operations = mock.Mock()
    operations.attach_mock(windows_kernel.UnmapViewOfFile, "unmap")
    operations.attach_mock(windows_kernel.CloseHandle, "close")
    with acpp._win_write_to_shared_named_memory(payload, 4242):
        assert windows_kernel.memory.raw == payload + b"\0" * (2048 - len(payload))
        assert operations.mock_calls == []
    windows_kernel.CreateFileMappingW.assert_called_once_with(
        -1, None, 0x4, 0, 2048, "__pydevd_pid_code_to_run__4242"
    )
    windows_kernel.MapViewOfFile.assert_called_once_with(0x12345678B, 0x2, 0, 0, 0)
    assert operations.mock_calls == [
        mock.call.unmap(windows_kernel.MapViewOfFile.return_value),
        mock.call.close(0x12345678B),
    ]


@pytest.mark.parametrize(
    "payload",
    [b"", b"x" * 2047, b"x" * 2048, "print(1)"],
    ids=["empty", "missing-terminator-space", "full-buffer", "not-bytes"],
)
def test_windows_shared_memory_rejects_invalid_payload(acpp, windows_kernel, payload):
    with pytest.raises(AssertionError):
        with acpp._win_write_to_shared_named_memory(payload, 4242):
            pytest.fail("Invalid code must not be written")
    windows_kernel.CreateFileMappingW.assert_not_called()


@pytest.mark.parametrize("failure", ["create", "map", "copy", "unmap", "close"])
def test_windows_shared_memory_errors(acpp, windows_kernel, monkeypatch, failure):
    if failure == "create":
        windows_kernel.CreateFileMappingW.return_value = None
    elif failure == "map":
        windows_kernel.MapViewOfFile.return_value = None
    elif failure == "copy":
        monkeypatch.setattr(
            acpp.ctypes, "memmove", mock.Mock(side_effect=RuntimeError("copy failed"))
        )
    elif failure == "unmap":
        windows_kernel.UnmapViewOfFile.return_value = False
    else:
        windows_kernel.CloseHandle.return_value = False
    expected = RuntimeError if failure == "copy" else OSError
    with pytest.raises(expected) as exc:
        with acpp._win_write_to_shared_named_memory(b"print(1)", 4242):
            assert failure in ("unmap", "close")
    if failure != "copy":
        assert exc.value.errno == 5
    if failure == "create":
        windows_kernel.MapViewOfFile.assert_not_called()
        windows_kernel.CloseHandle.assert_not_called()
    else:
        windows_kernel.CloseHandle.assert_called_once_with(0x12345678B)
    if failure in ("create", "map"):
        windows_kernel.UnmapViewOfFile.assert_not_called()
    else:
        windows_kernel.UnmapViewOfFile.assert_called_once_with(
            windows_kernel.MapViewOfFile.return_value
        )


@pytest.mark.parametrize("helper", ["mutex", "event", "shared_memory"])
def test_windows_ipc_cleanup_on_body_error(acpp, windows_kernel, helper):
    contexts = {
        "mutex": acpp._acquire_mutex("mutex", 10),
        "event": acpp._create_win_event("event"),
        "shared_memory": acpp._win_write_to_shared_named_memory(b"print(1)", 4242),
    }
    with pytest.raises(RuntimeError, match="body failed"):
        with contexts[helper]:
            raise RuntimeError("body failed")
    handles = {"mutex": 0x12345678A, "event": 0x12345678C, "shared_memory": 0x12345678B}
    windows_kernel.CloseHandle.assert_called_once_with(handles[helper])
    if helper == "mutex":
        windows_kernel.ReleaseMutex.assert_called_once_with(0x12345678A)
    elif helper == "shared_memory":
        windows_kernel.UnmapViewOfFile.assert_called_once_with(
            windows_kernel.MapViewOfFile.return_value
        )


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
    acpp, windows_kernel, monkeypatch, target_arch, completed
):
    monkeypatch.setattr(acpp, "IS_WINDOWS", True)
    for name in (
        "winappdbg",
        "winappdbg.win32",
        "winappdbg.win32.kernel32",
        "winappdbg.win32.defines",
    ):
        monkeypatch.setitem(sys.modules, name, None)

    def query(handle, process, native):
        process._obj.value = {"x86": 0x014C, "amd64": 0x8664, "arm64": 0}[target_arch]
        native._obj.value = 0xAA64
        return True

    windows_kernel.IsWow64Process2.side_effect = query
    windows_kernel.WaitForSingleObject.side_effect = [0, 0 if completed else 0x102]
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
    windows_kernel.CreateMutexW.assert_called_once_with(
        None, False, "_pydevd_pid_attach_mutex_4242"
    )
    windows_kernel.CreateEventW.assert_called_once_with(
        None, False, False, "_pydevd_pid_event_4242"
    )
    assert windows_kernel.memory.raw == b"print(1)" + b"\0" * (2048 - len(b"print(1)"))
    assert windows_kernel.WaitForSingleObject.call_args_list == [
        mock.call(0x12345678A, 10000),
        mock.call(0x12345678C, 15000),
    ]
    assert windows_kernel.CloseHandle.call_args_list == [
        mock.call(0x123456789),
        mock.call(0x12345678C),
        mock.call(0x12345678B),
        mock.call(0x12345678A),
    ]
    windows_kernel.ReleaseMutex.assert_called_once_with(0x12345678A)
    windows_kernel.UnmapViewOfFile.assert_called_once_with(
        windows_kernel.MapViewOfFile.return_value
    )
