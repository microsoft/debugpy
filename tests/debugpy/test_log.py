# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, division, print_function, unicode_literals

import contextlib
import pytest

from tests import debug
from tests.debug import runners, targets


@contextlib.contextmanager
def check_logs(tmpdir, run):
    expected_logs = {
        "debugpy.adapter-*.log": 1,
        "debugpy.launcher-*.log": 1 if run.request == "launch" else 0,
        # For attach_by_pid, there's ptvsd.server process that performs the injection,
        # and then there's the debug server that is injected into the debuggee.
        "debugpy.server-*.log": 2 if type(run).__name__ == "attach_by_pid" else 1,
    }

    actual_logs = lambda: {
        filename: len(tmpdir.listdir(filename)) for filename in expected_logs
    }

    assert actual_logs() == {filename: 0 for filename in expected_logs}
    yield
    assert actual_logs() == expected_logs


@pytest.mark.parametrize("target", targets.all)
@pytest.mark.parametrize("method", ["api", "cli"])
def test_log_dir(pyfile, tmpdir, target, method):
    @pyfile
    def code_to_debug():
        import debuggee

        debuggee.setup()

    # Depending on the method, attach_by_socket will use either `debugpy --log-dir ...`
    # or `debugpy.log_to() ...`.
    run = runners.attach_by_socket[method].with_options(log_dir=tmpdir.strpath)
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
            session.spawn_adapter.env["DEBUGPY_LOG_DIR"] = tmpdir
            if run.request != "launch":
                session.spawn_debuggee.env["DEBUGPY_LOG_DIR"] = tmpdir

            backchannel = session.open_backchannel()
            with run(session, target(code_to_debug)):
                pass

            backchannel.send("proceed")
