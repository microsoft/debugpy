# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import contextlib
import os
import sys

import pytest

import debugpy
from debugpy.common import log
from tests import debug
from tests.debug import runners, targets


def test_environment_description_does_not_raise_internal_exceptions(monkeypatch):
    from importlib import metadata as importlib_metadata

    monkeypatch.delattr(sys, "real_prefix", raising=False)
    monkeypatch.setattr(importlib_metadata, "distributions", lambda: ())

    debugpy_root = os.path.dirname(debugpy.__file__)
    real_prefix_exceptions = []

    def trace(frame, event, arg):
        # Only record AttributeErrors that mention ``real_prefix``. ``exception``
        # events fire for every exception raised in a debugpy frame, including
        # ones that unrelated environment probes intentionally raise and catch
        # (e.g. ``site.getsitepackages()``), so an unfiltered assertion would be
        # environment-dependent. Narrow it to the behavior this test targets.
        if event == "exception" and frame.f_code.co_filename.startswith(debugpy_root):
            exc = arg[1]
            if isinstance(exc, AttributeError) and "real_prefix" in str(exc):
                real_prefix_exceptions.append(exc)
        return trace

    previous_trace = sys.gettrace()
    sys.settrace(trace)
    try:
        description = log.get_environment_description("Environment:")
    finally:
        sys.settrace(previous_trace)

    assert "sys.real_prefix: <missing>" in description
    assert real_prefix_exceptions == []


@contextlib.contextmanager
def check_logs(tmpdir, run):
    # For attach_pid, there's ptvsd.server process that performs the injection,
    # and then there's the debug server that is injected into the debuggee.
    server_count = 2 if type(run).__name__ == "attach_pid" else 1

    expected_logs = {
        "debugpy.adapter-*.log": 1,
        "debugpy.launcher-*.log": 1 if run.request == "launch" else 0,
        "debugpy.pydevd.*.log": server_count,
        "debugpy.server-*.log": server_count,
    }

    actual_logs = lambda: {
        filename: len(tmpdir.listdir(filename)) for filename in expected_logs
    }

    assert actual_logs() == {filename: 0 for filename in expected_logs}
    yield
    assert actual_logs() == expected_logs


@pytest.mark.parametrize("run", runners.all_attach_socket)
@pytest.mark.parametrize("target", targets.all)
def test_log_dir(pyfile, tmpdir, run, target):
    @pyfile
    def code_to_debug():
        import debuggee

        debuggee.setup()

    # Depending on the method, the runner will use either `debugpy --log-dir ...`
    # or `debugpy.log_to() ...`.
    run = run.with_options(log_dir=tmpdir.strpath)
    with check_logs(tmpdir, run):
        with debug.Session() as session:
            session.log_dir = None

            with run(session, target(code_to_debug)):
                pass


@pytest.mark.parametrize("run", runners.all)
@pytest.mark.parametrize("target", targets.all)
def test_log_dir_env(pyfile, tmpdir, run, target):
    @pyfile
    def code_to_debug():
        import debuggee
        from debuggee import backchannel

        debuggee.setup()
        assert backchannel.receive() == "proceed"

    with check_logs(tmpdir, run):
        with debug.Session() as session:
            session.log_dir = None
            session.spawn_adapter.env["DEBUGPY_LOG_DIR"] = tmpdir.strpath
            if run.request != "launch":
                session.spawn_debuggee.env["DEBUGPY_LOG_DIR"] = tmpdir.strpath

            backchannel = session.open_backchannel()
            with run(session, target(code_to_debug)):
                pass

            backchannel.send("proceed")
