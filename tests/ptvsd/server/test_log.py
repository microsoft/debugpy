# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import contextlib
import pytest

from tests import debug


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

    with debug.Session() as session:
        with check_logs(tmpdir, session):
            if cli == "arg":
                session.log_dir = str(tmpdir)
            else:
                session.env["PTVSD_LOG_DIR"] = str(tmpdir)
            session.initialize(
                target=(run_as, code_to_debug), start_method=start_method
            )
            session.start_debugging()
            session.wait_for_exit()


def test_log_api(pyfile, tmpdir, run_as):
    @pyfile
    def code_to_debug():
        # import sys
        import debug_me  # noqa

        # import_and_enable_debugger(log_dir=str(sys.argv[1]))

    with debug.Session() as session:
        with check_logs(tmpdir, session):
            session.program_args += [str(tmpdir)]
            session.initialize(
                target=(run_as, code_to_debug), start_method="attach_socket_import"
            )
            session.start_debugging()
            session.wait_for_exit()
