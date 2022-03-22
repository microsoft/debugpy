#!/usr/bin/env python

# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import os
import os.path
import setuptools
import subprocess
import sys


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import versioneer  # noqa

del sys.path[0]

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
import debugpy
import debugpy._vendored

del sys.path[0]


PYDEVD_ROOT = debugpy._vendored.project_root("pydevd")
DEBUGBY_ROOT = os.path.dirname(os.path.abspath(debugpy.__file__))


def get_buildplatform():
    if "-p" in sys.argv:
        return sys.argv[sys.argv.index("-p") + 1]
    return None


def cython_build():
    print("Compiling extension modules (set SKIP_CYTHON_BUILD=1 to omit)")
    subprocess.call(
        [
            sys.executable,
            os.path.join(PYDEVD_ROOT, "setup_pydevd_cython.py"),
            "build_ext",
            "-i",
        ]
    )


def iter_vendored_files():
    # Add pydevd files as data files for this package. They are not
    # treated as a package of their own, because we don't actually
    # want to provide pydevd - just use our own copy internally.
    for project in debugpy._vendored.list_all():
        for filename in debugpy._vendored.iter_packaging_files(project):
            yield filename


# bdist_wheel determines whether the package is pure or not based on ext_modules.
# However, all pydevd native modules are prebuilt and packaged as data, so they
# should not be in the list.
#
# The proper way to handle this is by overriding has_ext_modules. However, due to
# https://bugs.python.org/issue32957, in setuptools 57.0.0 and below, it is not
# always called when it should be, with ext_modules tested directly instead.
#
# So, for non-pure builds, we provide a customized empty list for ext_modules that
# tests as truthful - this causes the package to be treated as non-pure on all
# relevant setuptools versions.
class ExtModules(list):
    def __bool__(self):
        return True


def override_build(cmds):
    def finalize_options(self):
        # Mark all packages as pure if requested to build a universal wheel.
        # Otherwise, bdist_wheel will silently ignore the request.
        bdist_wheel = self.distribution.get_command_obj("bdist_wheel", 0)
        if bdist_wheel is not None and bdist_wheel.universal:
            self.distribution.ext_modules = []
            self.distribution.has_ext_modules = lambda: False
        original(self)

    try:
        build = cmds["build"]
    except KeyError:
        from distutils.command.build import build
    original = build.finalize_options
    build.finalize_options = finalize_options


def override_build_py(cmds):
    # Filter platform-specific binaries in data files for binary builds.
    def finalize_options(self):
        original(self)

        # Don't filter anything for universal wheels.
        if not self.distribution.ext_modules:
            return

        plat = self.get_finalized_command("build").plat_name
        data_files = self.data_files

        def is_applicable(filename):
            def tail_is(*suffixes):
                return any((filename.endswith(ext) for ext in suffixes))

            if tail_is(".dylib"):
                return plat.startswith("macosx")
            if tail_is(".exe", ".dll", ".pdb", ".pyd"):
                return plat in ("win32", "win-amd64")
            if tail_is("-i386-linux-gnu.so", "_linux_x86.so"):
                return plat == "linux-i686"
            if tail_is("-x86_64-linux-gnu.so", "_linux_amd64.so"):
                return plat == "linux-x86_64"
            return True

        self.data_files = [
            (package, src_dir, build_dir, list(filter(is_applicable, filenames)))
            for package, src_dir, build_dir, filenames in data_files
        ]

    try:
        build_py = cmds["build_py"]
    except KeyError:
        from setuptools.command.build_py import build_py

    original = build_py.finalize_options
    build_py.finalize_options = finalize_options


with open("DESCRIPTION.md", "r") as fh:
    long_description = fh.read()


if __name__ == "__main__":
    if not os.getenv("SKIP_CYTHON_BUILD"):
        cython_build()

    extras = {}
    platforms = get_buildplatform()
    if platforms is not None:
        extras["platforms"] = platforms

    cmds = versioneer.get_cmdclass()
    override_build(cmds)
    override_build_py(cmds)

    setuptools.setup(
        name="debugpy",
        version=versioneer.get_version(),
        description="An implementation of the Debug Adapter Protocol for Python",  # noqa
        long_description=long_description,
        long_description_content_type="text/markdown",
        license="MIT",
        author="Microsoft Corporation",
        author_email="ptvshelp@microsoft.com",
        url="https://aka.ms/debugpy",
        project_urls={
            "Source": "https://github.com/microsoft/debugpy",
        },
        python_requires=">=3.7",
        classifiers=[
            "Development Status :: 5 - Production/Stable",
            "Programming Language :: Python :: 3.7",
            "Programming Language :: Python :: 3.8",
            "Programming Language :: Python :: 3.9",
            "Programming Language :: Python :: 3.10",
            "Topic :: Software Development :: Debuggers",
            "Operating System :: Microsoft :: Windows",
            "Operating System :: MacOS",
            "Operating System :: POSIX",
            "License :: OSI Approved :: Eclipse Public License 2.0 (EPL-2.0)",
            "License :: OSI Approved :: MIT License",
        ],
        package_dir={"": "src"},
        packages=[
            "debugpy",
            "debugpy.adapter",
            "debugpy.common",
            "debugpy.launcher",
            "debugpy.server",
            "debugpy._vendored",
        ],
        package_data={
            "debugpy": ["ThirdPartyNotices.txt"],
            "debugpy._vendored": list(iter_vendored_files()),
        },
        ext_modules=ExtModules(),
        has_ext_modules=lambda: True,
        cmdclass=cmds,
        **extras
    )
