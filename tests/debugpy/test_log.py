# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import contextlib
import pytest

from tests import debug
from tests.debug import runners, targets


@contextlib.contextmanager
def check_logs(tmpdir, run, pydevd_log):
    # For attach_pid, there's ptvsd.server process that performs the injection,
    # and then there's the debug server that is injected into the debuggee.
    server_count = 2 if type(run).__name__ == "attach_pid" else 1

    expected_logs = {
        "debugpy.adapter-*.log": 1,
        "debugpy.launcher-*.log": 1 if run.request == "launch" else 0,
        "debugpy.pydevd.*.log": server_count if pydevd_log else 0,
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
    with check_logs(tmpdir, run, pydevd_log=False):
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

    with check_logs(tmpdir, run, pydevd_log=True):
        with debug.Session() as session:
            session.log_dir = None
            session.spawn_adapter.env["DEBUGPY_LOG_DIR"] = tmpdir.strpath
            if run.request != "launch":
                session.spawn_debuggee.env["DEBUGPY_LOG_DIR"] = tmpdir.strpath

            backchannel = session.open_backchannel()
            with run(session, target(code_to_debug)):
                pass

            backchannel.send("proceed")
