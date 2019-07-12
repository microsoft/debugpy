# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import pytest

from ptvsd.common import log
from ptvsd.common.compat import reload
from ptvsd.server import options, __main__
from tests.patterns import some


EXPECTED_EXTRA = ["--"]


@pytest.mark.parametrize("target_kind", ["file", "module", "code"])
@pytest.mark.parametrize("client", ["", "client"])
@pytest.mark.parametrize("wait", ["", "wait"])
@pytest.mark.parametrize("nodebug", ["", "nodebug"])
@pytest.mark.parametrize("multiproc", ["", "multiproc"])
@pytest.mark.parametrize("extra", ["", "extra"])
def test_targets(target_kind, client, wait, nodebug, multiproc, extra):
    args = ["--host", "localhost", "--port", "8888"]

    if client:
        args += ["--client"]

    if wait:
        args += ["--wait"]

    if nodebug:
        args += ["--nodebug"]

    if multiproc:
        args += ["--multiprocess"]

    if target_kind == "file":
        target = "spam.py"
        args += [target]
    elif target_kind == "module":
        target = "spam"
        args += ["-m", target]
    elif target_kind == "code":
        target = "123"
        args += ["-c", target]

    if extra:
        extra = [
            "ham",
            "--client",
            "--wait",
            "-y",
            "spam",
            "--",
            "--nodebug",
            "--host",
            "--port",
            "-c",
            "--something",
            "-m",
        ]
        args += extra
    else:
        extra = []

    log.debug("args = {0!r}", args)
    reload(options)
    rest = __main__.parse(args)
    assert list(rest) == extra
    assert vars(options) == some.dict.containing(
        {
            "target_kind": target_kind,
            "target": target,
            "host": "localhost",
            "port": 8888,
            "no_debug": bool(nodebug),
            "wait": bool(wait),
            "multiprocess": bool(multiproc),
        }
    )


def test_unsupported_arg():
    reload(options)
    with pytest.raises(Exception):
        __main__.parse(["--port", "8888", "--xyz", "123", "spam.py"])


def test_host_required():
    reload(options)
    with pytest.raises(Exception):
        __main__.parse(["--port", "8888", "-m", "spam"])


def test_host_empty():
    reload(options)
    __main__.parse(["--host", "", "--port", "8888", "spam.py"])
    assert options.host == ""


def test_port_default():
    reload(options)
    __main__.parse(["--host", "localhost", "spam.py"])
    assert options.port == 5678
