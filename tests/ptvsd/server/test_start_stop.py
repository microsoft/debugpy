# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import platform
import pytest
import sys

from tests import debug
from tests.patterns import some


@pytest.mark.parametrize("start_method", ["launch"])
@pytest.mark.skipif(
    sys.version_info < (3, 0) and platform.system() == "Windows",
    reason="On Windows + Python 2, unable to send key strokes to test.",
)
@pytest.mark.skip("https://github.com/microsoft/ptvsd/issues/1571")
def test_wait_on_normal_exit_enabled(pyfile, start_method, run_as):
    @pyfile
    def code_to_debug():
        from debug_me import ptvsd

        ptvsd.break_into_debugger()
        print()  # line on which it'll actually break

    with debug.Session() as session:
        session.initialize(
            target=(run_as, code_to_debug),
            start_method=start_method,
            debug_options=["WaitOnNormalExit"],
            expected_returncode=some.int,
        )
        session.start_debugging()

        session.wait_for_stop()
        session.request_continue()

        session.process.stdin.write(b" \r\n")
        session.wait_for_exit()

        assert any(s.startswith("Press") for s in session.stdout_lines("utf-8"))


@pytest.mark.parametrize("start_method", ["launch"])
@pytest.mark.skipif(
    sys.version_info < (3, 0) and platform.system() == "Windows",
    reason="On Windows + Python 2, unable to send key strokes to test.",
)
@pytest.mark.skip("https://github.com/microsoft/ptvsd/issues/1571")
def test_wait_on_abnormal_exit_enabled(pyfile, start_method, run_as):
    @pyfile
    def code_to_debug():
        from debug_me import backchannel, ptvsd
        import sys

        ptvsd.break_into_debugger()
        backchannel.send("done")
        sys.exit(12345)

    with debug.Session() as session:
        backchannel = session.setup_backchannel()
        session.initialize(
            target=(run_as, code_to_debug),
            start_method=start_method,
            debug_options=["WaitOnAbnormalExit"],
            expected_returncode=some.int,
        )
        session.start_debugging()

        session.wait_for_stop()
        session.request_continue()

        assert backchannel.receive() == "done"

        session.process.stdin.write(b" \r\n")
        session.wait_for_exit()

        assert any(s.startswith("Press") for s in session.stdout_lines("utf-8"))


@pytest.mark.parametrize("start_method", ["launch"])
def test_exit_normally_with_wait_on_abnormal_exit_enabled(pyfile, start_method, run_as):
    @pyfile
    def code_to_debug():
        from debug_me import backchannel, ptvsd

        ptvsd.break_into_debugger()
        backchannel.send("done")

    with debug.Session() as session:
        backchannel = session.setup_backchannel()
        session.initialize(
            target=(run_as, code_to_debug),
            start_method=start_method,
            debug_options=["WaitOnAbnormalExit"],
        )
        session.start_debugging()

        session.wait_for_stop()
        session.request_continue()

        session.wait_for_termination()
        assert backchannel.receive() == "done"
        session.wait_for_exit()
