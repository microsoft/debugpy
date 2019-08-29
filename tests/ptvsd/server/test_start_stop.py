# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import platform
import pytest
import sys

from tests import debug, start_methods


@pytest.mark.parametrize("start_method", [start_methods.Launch])
@pytest.mark.skipif(
    sys.version_info < (3, 0) and platform.system() == "Windows",
    reason="On Windows + Python 2, unable to send key strokes to test.",
)
def test_wait_on_normal_exit_enabled(pyfile, start_method, run_as):
    @pyfile
    def code_to_debug():
        from debug_me import ptvsd

        ptvsd.break_into_debugger()
        print()  # line on which it'll actually break

    with debug.Session(start_method) as session:
        session.configure(
            run_as, code_to_debug,
            waitOnNormalExit=True,
        )
        session.start_debugging()

        session.wait_for_stop()
        session.request_continue()

        session.process.stdin.write(b" \r\n")

    assert any(s.startswith("Press") for s in session.stdout_lines("utf-8"))


@pytest.mark.parametrize("start_method", [start_methods.Launch])
@pytest.mark.skipif(
    sys.version_info < (3, 0) and platform.system() == "Windows",
    reason="On Windows + Python 2, unable to send key strokes to test.",
)
def test_wait_on_abnormal_exit_enabled(pyfile, start_method, run_as):
    @pyfile
    def code_to_debug():
        from debug_me import backchannel, ptvsd
        import sys

        ptvsd.break_into_debugger()
        backchannel.send("done")
        sys.exit(12345)

    with debug.Session(start_method, backchannel=True) as session:
        backchannel = session.backchannel
        session.expected_exit_code = 12345
        session.configure(
            run_as, code_to_debug,
            waitOnAbnormalExit=True,
        )
        session.start_debugging()

        session.wait_for_stop()
        session.request_continue()

        assert backchannel.receive() == "done"

        session.process.stdin.write(b" \r\n")

    assert any(s.startswith("Press") for s in session.stdout_lines("utf-8"))


@pytest.mark.parametrize("start_method", [start_methods.Launch])
def test_exit_normally_with_wait_on_abnormal_exit_enabled(pyfile, start_method, run_as):
    @pyfile
    def code_to_debug():
        from debug_me import backchannel, ptvsd

        ptvsd.break_into_debugger()
        backchannel.send("done")

    with debug.Session(start_method, backchannel=True) as session:
        backchannel = session.backchannel
        session.configure(
            run_as, code_to_debug,
            waitOnAbnormalExit=True,
        )
        session.start_debugging()

        session.wait_for_stop()
        session.request_continue()

        session.wait_for_termination()
        assert backchannel.receive() == "done"
