# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import pytest

from ptvsd.common import log
from ptvsd.common.compat import reload

from ptvsd.server import main, options


@pytest.mark.parametrize("target_kind", ["file", "module", "code"])
@pytest.mark.parametrize("client", ["", "client"])
@pytest.mark.parametrize("wait", ["", "wait"])
@pytest.mark.parametrize("multiproc", ["", "multiproc"])
@pytest.mark.parametrize("extra", ["", "extra"])
def test_targets(target_kind, client, wait, multiproc, extra):
    args = ["--host", "localhost", "--port", "8888"]

    if client:
        args += ["--client"]

    if wait:
        args += ["--wait"]

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

    log.debug("args = {0!r}", args)
    reload(options)
    rest = list(main.parse(args))
    assert rest == extra

    expected_options = {
        "target_kind": target_kind,
        "target": target,
        "host": "localhost",
        "port": 8888,
        "wait": bool(wait),
        "multiprocess": bool(multiproc),
    }
    actual_options = {name: vars(options)[name] for name in expected_options}
    assert expected_options == actual_options


def test_unsupported_arg():
    reload(options)
    with pytest.raises(Exception):
        main.parse(["--port", "8888", "--xyz", "123", "spam.py"])


def test_host_required():
    reload(options)
    with pytest.raises(Exception):
        main.parse(["--port", "8888", "-m", "spam"])


def test_host_empty():
    reload(options)
    main.parse(["--host", "", "--port", "8888", "spam.py"])
    assert options.host == ""


def test_port_default():
    reload(options)
    main.parse(["--host", "localhost", "spam.py"])
    assert options.port == 5678
