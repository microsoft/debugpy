# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import errno
import os.path
import platform
import pytest
import subprocess
import sys

from ptvsd.common import launcher


launcher_py = os.path.abspath(launcher.__file__)


@pytest.mark.parametrize("run_as", ["file", "module", "code"])
@pytest.mark.parametrize("mode", ["normal", "abnormal", "normal+abnormal", ""])
@pytest.mark.parametrize("seperator", ["seperator", ""])
def test_launcher_parser(mode, seperator, run_as):
    args = []

    switch = mode.split("+")

    if "normal" in switch:
        args += [launcher.WAIT_ON_NORMAL_SWITCH]

    if "abnormal" in switch:
        args += [launcher.WAIT_ON_ABNORMAL_SWITCH]

    if seperator:
        args += ["--"]

    if run_as == "file":
        expected = ["myscript.py", "--arg1", "--arg2", "--arg3", "--", "more args"]
    elif run_as == "module":
        expected = ["-m", "myscript", "--arg1", "--arg2", "--arg3", "--", "more args"]
    else:
        expected = ["-c", "some code"]

    args += expected

    if seperator:
        actual = list(launcher.parse(args))
        assert actual == expected
    else:
        with pytest.raises(AssertionError):
            actual = launcher.parse(args)


@pytest.mark.parametrize("run_as", ["file", "module", "code"])
@pytest.mark.parametrize("mode", ["normal", "abnormal", "normal+abnormal", ""])
@pytest.mark.parametrize("exit_code", [0, 10])
@pytest.mark.timeout(5)
@pytest.mark.skipif(platform.system() == "Windows", reason="Not reliable on windows.")
def test_launcher(pyfile, mode, exit_code, run_as):
    @pyfile
    def code_to_run():
        import sys

        sys.exit(int(sys.argv[1]))

    args = [sys.executable, launcher_py]

    switch = mode.split("+")

    if "normal" in switch:
        args += [launcher.WAIT_ON_NORMAL_SWITCH]

    if "abnormal" in switch:
        args += [launcher.WAIT_ON_ABNORMAL_SWITCH]

    args += ["--"]

    if run_as == "file":
        args += [code_to_run.strpath, str(exit_code)]
    elif run_as == "module":
        args += ["-m", "code_to_run", str(exit_code)]
    else:
        with open(code_to_run.strpath, "r") as f:
            args += ["-c", f.read(), str(exit_code)]

    wait_for_user = (exit_code, mode) in [
        (0, "normal"),
        (10, "abnormal"),
        (0, "normal+abnormal"),
        (10, "normal+abnormal"),
    ]

    if platform.system() == "Windows":
        p = subprocess.Popen(
            args=args,
            cwd=os.path.dirname(code_to_run.strpath),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            # CREATE_NEW_CONSOLE is needed other wise you cannot write to stdin.
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
        # NOTE: We disabled this test on windows because there is no
        # reliable way to write to stdin without going though the Win32
        # WriteConsoleInput.
    else:
        p = subprocess.Popen(
            args=args,
            cwd=os.path.dirname(code_to_run.strpath),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
        )

    if wait_for_user:
        outstr = b""
        while not outstr.endswith(b". . . "):
            outstr += p.stdout.read(1)

        exc_type = BrokenPipeError if sys.version_info >= (3,) else IOError

        while p.poll() is None:
            try:
                p.stdin.write(b"\n")
                p.stdin.flush()
            except exc_type as exc:
                # This can occur if the process exits before write completes.
                if isinstance(exc, IOError) and exc.errno != errno.EPIPE:
                    raise
    else:
        p.wait()

    assert exit_code == p.returncode
