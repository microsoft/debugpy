# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

"""Native smoke entrypoint: run against the installed wheel, not a source overlay."""

import importlib
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import struct
import subprocess
import sys
import sysconfig
import time

import pytest
import pydevd_tracing
import debugpy

with importlib.import_module("debugpy._vendored").vendored("pydevd"):
    attach = importlib.import_module(
        "pydevd_attach_to_process.add_code_to_python_process"
    )

REQUIRE_ARM64 = os.environ.get("DEBUGPY_TEST_WINDOWS_ARM64") == "1"
pytestmark = pytest.mark.skipif(
    sys.platform != "win32" and not REQUIRE_ARM64, reason="Windows native helpers"
)


@pytest.fixture(autouse=True)
def require_native_arm64_when_requested():
    if REQUIRE_ARM64:
        assert sys.platform == "win32"
        assert (
            sysconfig.get_platform() == "win-arm64"
        ), "The ARM64 release gate must run with native ARM64 Python."
        source = Path(__file__).resolve().parents[3] / "src"
        assert (
            not Path(debugpy.__file__).resolve().is_relative_to(source)
        ), "The ARM64 release gate must use the installed wheel, not src."


def pe_machine(filename):
    with open(filename, "rb") as binary:
        assert binary.read(2) == b"MZ"
        binary.seek(0x3C)
        offset = struct.unpack("<I", binary.read(4))[0]
        binary.seek(offset)
        assert binary.read(4) == b"PE\0\0"
        return struct.unpack("<H", binary.read(2))[0]


def test_native_binaries_match_interpreter():
    cython = importlib.import_module("_pydevd_bundle.pydevd_cython")

    assert cython.__file__ is not None
    assert cython.__file__.endswith(".pyd"), "A compiled Cython extension is required."
    target = attach.get_windows_process_architecture(os.getpid())
    expected = {"x86": 0x014C, "amd64": 0x8664, "arm64": 0xAA64}[target]
    for prefix, extension in (
        ("attach_", ".dll"),
        ("run_code_on_dllmain_", ".dll"),
        ("inject_dll_", ".exe"),
    ):
        filename = attach.get_target_filename(
            prefix=prefix, extension=extension, target_arch=target
        )
        assert filename is not None
        assert pe_machine(filename) == expected
    assert pe_machine(cython.__file__) == expected
    assert (
        pydevd_tracing.get_python_helper_lib_filename()
        == attach.get_target_filename(target_arch=target)
    )
    if sys.version_info[:2] == (3, 10):
        frame_eval = importlib.import_module(
            "_pydevd_frame_eval.pydevd_frame_evaluator"
        )

        assert frame_eval.__file__ is not None
        assert frame_eval.__file__.endswith(".pyd")
        assert pe_machine(frame_eval.__file__) == expected


def test_native_windows_mutex_ownership():
    kernel32 = attach._get_windows_kernel32()
    name = f"_pydevd_pid_attach_mutex_{os.getpid()}"
    retained_handle = kernel32.CreateMutexW(None, False, name)
    assert retained_handle

    def acquire():
        with attach._acquire_mutex(name, 0):
            return True

    try:
        with ThreadPoolExecutor(max_workers=1) as worker:
            with attach._acquire_mutex(name, 1):
                with pytest.raises(attach.TimeoutError, match="Unable to acquire mutex"):
                    worker.submit(acquire).result(timeout=5)
            assert worker.submit(acquire).result(timeout=5)
    finally:
        assert kernel32.CloseHandle(retained_handle)


def test_native_windows_event_protocol():
    kernel32 = attach._get_windows_kernel32()
    kernel32.CreateEventA.argtypes = [
        attach.ctypes.c_void_p,
        attach.wintypes.BOOL,
        attach.wintypes.BOOL,
        attach.wintypes.LPCSTR,
    ]
    kernel32.CreateEventA.restype = attach.wintypes.HANDLE
    kernel32.SetEvent.argtypes = [attach.wintypes.HANDLE]
    kernel32.SetEvent.restype = attach.wintypes.BOOL
    name = f"_pydevd_pid_event_{os.getpid()}"
    with attach._create_win_event(name) as event:
        assert not event.wait_for_event_set(0)
        sender = kernel32.CreateEventA(None, False, False, name.encode("ascii"))
        assert sender
        try:
            assert kernel32.SetEvent(sender)
            assert event.wait_for_event_set(1)
            assert not event.wait_for_event_set(0)
        finally:
            assert kernel32.CloseHandle(sender)


def test_native_windows_shared_memory_protocol():
    kernel32 = attach._get_windows_kernel32()
    kernel32.OpenFileMappingA.argtypes = [
        attach.wintypes.DWORD,
        attach.wintypes.BOOL,
        attach.wintypes.LPCSTR,
    ]
    kernel32.OpenFileMappingA.restype = attach.wintypes.HANDLE
    pid = os.getpid()
    payload = b"print(1)"
    with attach._win_write_to_shared_named_memory(payload, pid):
        mapping = kernel32.OpenFileMappingA(
            0x4, False, f"__pydevd_pid_code_to_run__{pid}".encode("ascii")
        )
        assert mapping
        try:
            view = kernel32.MapViewOfFile(mapping, 0x4, 0, 0, 2048)
            assert view
            try:
                assert attach.ctypes.string_at(view, 2048) == (
                    payload + b"\0" * (2048 - len(payload))
                )
            finally:
                assert kernel32.UnmapViewOfFile(view)
        finally:
            assert kernel32.CloseHandle(mapping)


def test_native_pid_injection_executes_code(tmp_path, monkeypatch):
    assert attach.__file__ is not None
    monkeypatch.syspath_prepend(str(Path(attach.__file__).parent))
    result = tmp_path / "injected.txt"
    ready = tmp_path / "ready.txt"
    ready_temp = tmp_path / "ready.tmp"
    stop = tmp_path / "stop.txt"
    # Windows venv redirectors can launch Python under a different PID.
    child_code = (
        "import os, time\n"
        "from pathlib import Path\n"
        f"Path({str(ready_temp)!r}).write_text(str(os.getpid()))\n"
        f"Path({str(ready_temp)!r}).replace({str(ready)!r})\n"
        "deadline = time.monotonic() + 60\n"
        f"while not Path({str(stop)!r}).exists() and time.monotonic() < deadline:\n"
        "    time.sleep(0.05)\n"
    )
    process = subprocess.Popen([sys.executable, "-c", child_code])
    try:
        deadline = time.monotonic() + 15
        while not ready.exists() and time.monotonic() < deadline:
            assert process.poll() is None
            time.sleep(0.05)
        pid = int(ready.read_text())
        code = 'from pathlib import Path; Path("%s").write_text("injected")' % (
            str(result).replace("\\", "\\\\"),
        )
        attach.run_python_code_windows(pid, code)
        deadline = time.monotonic() + 15
        while not result.exists() and time.monotonic() < deadline:
            assert process.poll() is None
            time.sleep(0.05)
        assert result.read_text() == "injected"
    finally:
        stop.write_text("stop")
        process.wait(timeout=15)


@pytest.mark.skipif(
    sys.version_info[:2] > (3, 11),
    reason="CPython 3.12+ uses Python APIs instead of the tracing helper",
)
def test_native_tracing_reaches_existing_thread():
    # Isolate tracing and pydevd's helper cache from the test runner.
    code = r"""
import threading
import pydevd_tracing

ready = threading.Event()
proceed = threading.Event()
traced = threading.Event()

def work():
    ready.set()
    proceed.wait()
    marker()

def marker():
    pass

def trace(frame, event, arg):
    if event == "call" and frame.f_code.co_name == "marker":
        traced.set()
    return trace

worker = threading.Thread(target=work)
worker.start()
assert ready.wait(10)
try:
    assert pydevd_tracing._load_python_helper_lib() is not None
    assert pydevd_tracing.set_trace_to_threads(
        trace, [worker.ident], create_dummy_thread=False
    ) == 0
finally:
    proceed.set()
    worker.join(10)
assert not worker.is_alive()
assert traced.is_set(), "The existing thread did not execute the native tracer."
"""
    env = dict(os.environ)
    vendored_root = str(Path(pydevd_tracing.__file__).parent)
    env["PYTHONPATH"] = os.pathsep.join([vendored_root, env.get("PYTHONPATH", "")])
    subprocess.run([sys.executable, "-c", code], env=env, check=True, timeout=30)
