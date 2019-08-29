# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import contextlib
import pytest

from ptvsd.common import compat
from tests import debug, start_methods


@contextlib.contextmanager
def check_logs(tmpdir, session):
    assert not tmpdir.listdir("ptvsd-*.log")
    yield
    assert len(tmpdir.listdir("ptvsd-*.log")) == 1
    log_name = "ptvsd-{}.log".format(session.pid)
    assert tmpdir.join(log_name).size() > 0


@pytest.mark.parametrize("cli", ["arg", "env"])
def test_log_cli(pyfile, tmpdir, start_method, run_as, cli):
    if cli == "arg" and start_method == "attach_socket_import":
        pytest.skip()

    @pyfile
    def code_to_debug():
        import debug_me  # noqa

    with debug.Session(start_method) as session:
        with check_logs(tmpdir, session):
            if cli == "arg":
                session.log_dir = str(tmpdir)
            else:
                session.env["PTVSD_LOG_DIR"] = str(tmpdir)
            session.configure(run_as, code_to_debug)
            session.start_debugging()


@pytest.mark.parametrize("start_method", [start_methods.CustomServer])
def test_log_api(pyfile, tmpdir, start_method, run_as):
    @pyfile
    def code_to_debug():
        from debug_me import backchannel, ptvsd
        port, log_dir = backchannel.receive()
        ptvsd.enable_attach(("localhost", port), log_dir=log_dir)
        ptvsd.wait_for_attach()

    log_dir = compat.filename(tmpdir)
    with debug.Session(start_method, backchannel=True) as session:
        backchannel = session.backchannel

        @session.before_connect
        def before_connect():
            backchannel.send([session.ptvsd_port, log_dir])

        with check_logs(tmpdir, session):
            session.configure(run_as, code_to_debug)
            session.start_debugging()
