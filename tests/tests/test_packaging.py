# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import json
import os
from pathlib import Path
import runpy
import subprocess
import sys

import pytest
from setuptools import Distribution
from setuptools.command.build import build
from setuptools.command.build_py import build_py

ROOT = Path(__file__).resolve().parents[2]
WINDOWS_BINARIES = [
    f"pydevd/pydevd_attach_to_process/{name}_{arch}.{extension}"
    for arch in ("x86", "amd64", "arm64")
    for name, extension in (
        ("attach", "dll"),
        ("attach", "pdb"),
        ("inject_dll", "exe"),
        ("run_code_on_dllmain", "dll"),
    )
] + ["pydevd/_pydevd_bundle/pydevd_cython.cp311-win_arm64.pyd"]
LINUX_X86 = ["pydevd/attach_linux_x86.so", "pydevd/speedups-i386-linux-gnu.so"]
LINUX_X64 = ["pydevd/attach_linux_amd64.so", "pydevd/speedups-x86_64-linux-gnu.so"]
MAC = ["pydevd/attach.dylib"]
SOURCE = ["pydevd/pydevd.py"]
FILES = WINDOWS_BINARIES + LINUX_X86 + LINUX_X64 + MAC + SOURCE


@pytest.fixture
def packaging_command(tmp_path, monkeypatch):
    setup = runpy.run_path(str(ROOT / "setup.py"))
    # Exercise the actual child-process invocation without requiring a C compiler.
    (tmp_path / "setup_pydevd_cython.py").write_text(
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "Path(__file__).with_name('child.json').write_text(json.dumps({\n"
        "    'argv': sys.argv[1:],\n"
        "    'env': dict(os.environ),\n"
        "    'executable': sys.executable,\n"
        "}))\n"
        "sys.exit(int(os.environ.get('TEST_BUILD_EXIT_CODE', '0')))\n"
    )
    setup["override_build_py"].__globals__["PYDEVD_ROOT"] = str(tmp_path)
    monkeypatch.setattr(setup["debugpy"]._vendored, "list_all", lambda: ["pydevd"])
    monkeypatch.setattr(
        setup["debugpy"]._vendored, "iter_packaging_files", lambda project: FILES
    )

    class PackagingBuildPy(build_py):
        pass

    setup["override_build_py"]({"build_py": PackagingBuildPy})

    def create(platform, universal=False):
        distribution = Distribution(
            {
                "packages": ["debugpy._vendored"],
                "package_data": {"debugpy._vendored": []},
                "ext_modules": [] if universal else setup["ExtModules"](),
            }
        )
        build_command = distribution.get_command_obj("build")
        build_command.plat_name = platform
        command = PackagingBuildPy(distribution)
        command.ensure_finalized()
        return command.package_data["debugpy._vendored"]

    return create, tmp_path / "child.json"


@pytest.mark.parametrize(
    "platform, expected",
    [
        ("win32", WINDOWS_BINARIES + SOURCE),
        ("win-amd64", WINDOWS_BINARIES + SOURCE),
        ("win-arm64", WINDOWS_BINARIES + SOURCE),
        ("linux-i686", LINUX_X86 + SOURCE),
        ("linux-x86_64", LINUX_X64 + SOURCE),
        ("linux-aarch64", SOURCE),
        ("macosx-11.0-arm64", MAC + SOURCE),
        ("macosx-10.9-x86_64", MAC + SOURCE),
    ],
)
def test_platform_package_data(packaging_command, platform, expected):
    create, _ = packaging_command
    assert create(platform) == expected


def test_universal_wheel_keeps_all_data(packaging_command):
    create, _ = packaging_command
    assert create("win-arm64", universal=True) == FILES


def test_universal_build_clears_extensions():
    setup = runpy.run_path(str(ROOT / "setup.py"))

    class PackagingBuild(build):
        pass

    setup["override_build"]({"build": PackagingBuild})
    distribution = Distribution({"ext_modules": setup["ExtModules"]()})
    distribution.get_command_obj("bdist_wheel").universal = True
    PackagingBuild(distribution).ensure_finalized()
    assert not distribution.ext_modules
    assert not distribution.has_ext_modules()


def test_cython_subprocess_inherits_cross_target_configuration(
    packaging_command, monkeypatch, tmp_path
):
    config = tmp_path / "target.cfg"
    config.write_text("[build_ext]\nplat_name=win-arm64\n")
    settings = {
        "DIST_EXTRA_CONFIG": str(config),
        "VSCMD_ARG_TGT_ARCH": "arm64",
        "SETUPTOOLS_EXT_SUFFIX": ".cp311-win_arm64.pyd",
        "SETUPTOOLS_USE_DISTUTILS": "local",
        "REQUIRE_CYTHON_BUILD": "1",
    }
    for key, value in settings.items():
        monkeypatch.setenv(key, value)
    create, child_output = packaging_command
    create("win-arm64")
    child = json.loads(child_output.read_text())
    assert child["argv"] == ["build_ext", "--inplace"]
    assert os.path.samefile(child["executable"], sys.executable)
    assert {key: child["env"][key] for key in settings} == settings


def test_required_cython_failure_is_not_silently_ignored(
    packaging_command, monkeypatch
):
    monkeypatch.setenv("REQUIRE_CYTHON_BUILD", "1")
    monkeypatch.setenv("TEST_BUILD_EXIT_CODE", "7")
    create, _ = packaging_command
    with pytest.raises(subprocess.CalledProcessError) as exc:
        create("win-arm64")
    assert exc.value.returncode == 7


def test_optional_cython_failure_keeps_packaging(packaging_command, monkeypatch):
    monkeypatch.setenv("REQUIRE_CYTHON_BUILD", "0")
    monkeypatch.setenv("TEST_BUILD_EXIT_CODE", "7")
    create, _ = packaging_command
    assert create("win-arm64") == WINDOWS_BINARIES + SOURCE
