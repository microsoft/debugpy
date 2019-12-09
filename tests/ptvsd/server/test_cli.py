# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, division, print_function, unicode_literals

import pickle
import pytest
import subprocess
import sys

from ptvsd.common import log


@pytest.fixture
def cli(pyfile):
    @pyfile
    def cli_parser():
        import os
        import pickle
        import sys
        from ptvsd.server import cli, options

        try:
            sys.argv[1:] = cli.parse(sys.argv[1:])
        except Exception as exc:
            os.write(1, pickle.dumps(exc))
            sys.exit(1)
        else:
            # We only care about options that correspond to public switches.
            options = {
                name: getattr(options, name)
                for name in [
                    "target_kind",
                    "target",
                    "host",
                    "port",
                    "client",
                    "wait",
                    "multiprocess",
                ]
            }
            os.write(1, pickle.dumps([sys.argv[1:], options]))

    def parse(args):
        log.debug("Parsing argv: {0!r}", args)
        try:
            output = subprocess.check_output(
                [sys.executable, "-u", cli_parser.strpath] + args
            )
            argv, options = pickle.loads(output)
        except subprocess.CalledProcessError as exc:
            raise pickle.loads(exc.output)

        log.debug("Adjusted sys.argv: {0!r}", argv)
        log.debug("Parsed options: {0!r}", options)
        return argv, options

    return parse


@pytest.mark.parametrize("target_kind", ["file", "module", "code"])
@pytest.mark.parametrize("port", ["", "8888"])
@pytest.mark.parametrize("client", ["", "client"])
@pytest.mark.parametrize("wait", ["", "wait"])
@pytest.mark.parametrize("subprocesses", ["", "subprocesses"])
@pytest.mark.parametrize("extra", ["", "extra"])
def test_targets(cli, target_kind, port, client, wait, subprocesses, extra):
    args = ["--host", "localhost"]

    if port:
        args += ["--port", port]

    if client:
        args += ["--client"]

    if wait:
        args += ["--wait"]

    if not subprocesses:
        args += ["--no-subprocesses"]

    if target_kind == "file":
        target = "spam.py"
        args += [target]
    elif target_kind == "module":
        target = "spam"
        args += ["-m", target]
    elif target_kind == "code":
        target = "123"
        args += ["-c", target]
    else:
        pytest.fail(target_kind)

    if extra:
        extra = [
            "ham",
            "--client",
            "--wait",
            "-y",
            "spam",
            "--",
            "--host",
            "--port",
            "-c",
            "--something",
            "-m",
        ]
        args += extra
    else:
        extra = []

    argv, options = cli(args)

    assert argv == extra
    assert options == {
        "target_kind": target_kind,
        "target": target,
        "host": "localhost",
        "port": int(port) if port else 5678,
        "wait": bool(wait),
        "multiprocess": bool(subprocesses),
        "client": bool(client),
    }


def test_unsupported_arg(cli):
    with pytest.raises(Exception):
        cli(["--port", "8888", "--xyz", "123", "spam.py"])


def test_host_required(cli):
    with pytest.raises(Exception):
        cli(["--port", "8888", "-m", "spam"])


def test_host_empty(cli):
    _, options = cli(["--host", "", "--port", "8888", "spam.py"])
    assert options["host"] == ""
