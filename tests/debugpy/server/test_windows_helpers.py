# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import os
from pathlib import Path
import runpy
import subprocess
import sys
from unittest import mock

import pytest
import pydevd_tracing


@pytest.fixture(autouse=True)
def isolated_build_environment():
    with mock.patch.dict(os.environ):
        yield


@pytest.fixture
def build_helper(monkeypatch):
    vswhere = mock.Mock(spec=["get_latest_path"])
    vswhere.get_latest_path.return_value = None
    monkeypatch.setitem(sys.modules, "vswhere", vswhere)
    root = Path(__file__).resolve().parents[3]
    return runpy.run_path(str(root / "build_attach_binaries.py"))


@pytest.mark.parametrize("os_arch", ["ARM64", "AMD64", "x86"])
@pytest.mark.parametrize(
    "interpreter, bits, suffix",
    [
        ("win-arm64", True, "arm64"),
        ("win-amd64", True, "amd64"),
        ("win32", False, "x86"),
    ],
)
def test_tracing_selects_interpreter_architecture(
    monkeypatch, os_arch, interpreter, bits, suffix
):
    monkeypatch.setattr(pydevd_tracing, "IS_WINDOWS", True)
    monkeypatch.setattr(pydevd_tracing, "IS_64BIT_PROCESS", bits)
    monkeypatch.setenv("PROCESSOR_ARCHITECTURE", os_arch)
    monkeypatch.setenv("PROCESSOR_ARCHITEW6432", os_arch)
    monkeypatch.setattr(pydevd_tracing.sysconfig, "get_platform", lambda: interpreter)
    with mock.patch.object(pydevd_tracing.os.path, "exists", return_value=True):
        filename = pydevd_tracing.get_python_helper_lib_filename()
    assert filename is not None
    assert os.path.basename(filename) == f"attach_{suffix}.dll"


def test_tracing_missing_arm64_helper_does_not_load_x64(monkeypatch):
    monkeypatch.setattr(pydevd_tracing, "IS_WINDOWS", True)
    monkeypatch.setattr(pydevd_tracing, "IS_64BIT_PROCESS", True)
    monkeypatch.setattr(pydevd_tracing.sysconfig, "get_platform", lambda: "win-arm64")
    with mock.patch.object(
        pydevd_tracing.os.path,
        "exists",
        side_effect=lambda path: not path.endswith("attach_arm64.dll"),
    ):
        assert pydevd_tracing.get_python_helper_lib_filename() is None


@pytest.mark.parametrize("target", ["win-arm64", "win-amd64", "win32"])
def test_build_helper_requests_arm64_only_when_native(
    monkeypatch, build_helper, target
):
    module = build_helper
    monkeypatch.setattr(module["platform"], "system", lambda: "Windows")
    monkeypatch.setattr(module["sysconfig"], "get_platform", lambda: target)
    with mock.patch.object(module["os"].path, "exists", return_value=False):
        with mock.patch.object(module["subprocess"], "check_call") as check_call:
            module["build_pydevd_binaries"](False)
    command = check_call.call_args.args[0]
    assert command[0].endswith(os.path.join("windows", "compile_windows.bat"))
    assert command[1:] == (["arm64"] if target == "win-arm64" else [])


def test_build_helper_propagates_failure(monkeypatch, build_helper):
    module = build_helper
    monkeypatch.setattr(module["platform"], "system", lambda: "Windows")
    with mock.patch.object(
        module["subprocess"],
        "check_call",
        side_effect=subprocess.CalledProcessError(1, "compile_windows.bat"),
    ):
        with pytest.raises(subprocess.CalledProcessError):
            module["build_pydevd_binaries"](True)


def test_build_helper_rebuilds_incomplete_arm64_outputs(monkeypatch, build_helper):
    module = build_helper
    monkeypatch.setattr(module["platform"], "system", lambda: "Windows")
    monkeypatch.setattr(module["sysconfig"], "get_platform", lambda: "win-arm64")
    with mock.patch.object(
        module["os"].path,
        "exists",
        side_effect=lambda path: not path.endswith("inject_dll_arm64.exe"),
    ):
        with mock.patch.object(module["subprocess"], "check_call") as check_call:
            module["build_pydevd_binaries"](False)
    assert check_call.call_args.args[0][1:] == ["arm64"]
