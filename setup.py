#!/usr/bin/env python

# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import os
import os.path
import subprocess
import sys


pure = None
if "--pure" in sys.argv:
    pure = True
    sys.argv.remove("--pure")
elif "--universal" in sys.argv:
    pure = True
elif "--abi" in sys.argv:
    pure = False
    sys.argv.remove("--abi")


from setuptools import setup  # noqa

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
            os.path.join(PYDEVD_ROOT, "setup_cython.py"),
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


with open("DESCRIPTION.md", "r") as fh:
    long_description = fh.read()


try:
    from wheel.bdist_wheel import bdist_wheel as _bdist_wheel

    class bdist_wheel(_bdist_wheel):
        def finalize_options(self):
            _bdist_wheel.finalize_options(self)
            self.root_is_pure = pure


except ImportError:
    bdist_wheel = None

if __name__ == "__main__":
    if not os.getenv("SKIP_CYTHON_BUILD"):
        cython_build()

    cmds = versioneer.get_cmdclass()
    cmds["bdist_wheel"] = bdist_wheel

    extras = {}
    platforms = get_buildplatform()
    if platforms is not None:
        extras["platforms"] = platforms

    setup(
        name="debugpy",
        version=versioneer.get_version(),
        description="An implementation of the Debug Adapter Protocol for Python",  # noqa
        long_description=long_description,
        long_description_content_type="text/markdown",
        license="MIT",
        author="Microsoft Corporation",
        author_email="ptvshelp@microsoft.com",
        url="https://aka.ms/debugpy",
        python_requires=">=2.7,!=3.0.*,!=3.1.*,!=3.2.*,!=3.3.*,!=3.4.*",
        classifiers=[
            "Development Status :: 5 - Production/Stable",
            "Programming Language :: Python :: 2.7",
            "Programming Language :: Python :: 3.5",
            "Programming Language :: Python :: 3.6",
            "Programming Language :: Python :: 3.7",
            "Programming Language :: Python :: 3.8",
            "Programming Language :: Python :: 3.9",
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
        cmdclass=cmds,
        **extras
    )
