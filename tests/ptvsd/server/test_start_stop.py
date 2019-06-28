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
    reason="On Win32 Python2.7, unable to send key strokes to test.",
)
def test_wait_on_normal_exit_enabled(pyfile, start_method, run_as):
    @pyfile
    def code_to_debug():
        from debug_me import backchannel
        import ptvsd

        ptvsd.break_into_debugger()
        backchannel.write_json("done")

    with debug.Session() as session:
        session.initialize(
            target=(run_as, code_to_debug),
            start_method=start_method,
            debug_options=["WaitOnNormalExit"],
            use_backchannel=True,
        )
        session.start_debugging()

        session.wait_for_thread_stopped()
        session.send_request("continue").wait_for_response(freeze=False)

        session.expected_returncode = some.int
        assert session.read_json() == "done"

        session.process.stdin.write(b" \r\n")
        session.wait_for_exit()

        decoded = "\n".join(
            (x.decode("utf-8") if isinstance(x, bytes) else x)
            for x in session.output_data["OUT"]
        )

        assert "Press" in decoded


@pytest.mark.parametrize("start_method", ["launch"])
@pytest.mark.skipif(
    sys.version_info < (3, 0) and platform.system() == "Windows",
    reason="On windows py2.7 unable to send key strokes to test.",
)
def test_wait_on_abnormal_exit_enabled(pyfile, start_method, run_as):
    @pyfile
    def code_to_debug():
        from debug_me import backchannel
        import sys
        import ptvsd

        ptvsd.break_into_debugger()
        backchannel.write_json("done")
        sys.exit(12345)

    with debug.Session() as session:
        session.initialize(
            target=(run_as, code_to_debug),
            start_method=start_method,
            debug_options=["WaitOnAbnormalExit"],
            use_backchannel=True,
        )
        session.start_debugging()

        session.wait_for_thread_stopped()
        session.send_request("continue").wait_for_response(freeze=False)

        session.expected_returncode = some.int
        assert session.read_json() == "done"

        session.process.stdin.write(b" \r\n")
        session.wait_for_exit()

        def _decode(text):
            if isinstance(text, bytes):
                return text.decode("utf-8")
            return text

        assert any(
            l for l in session.output_data["OUT"] if _decode(l).startswith("Press")
        )


@pytest.mark.parametrize("start_method", ["launch"])
def test_exit_normally_with_wait_on_abnormal_exit_enabled(pyfile, start_method, run_as):
    @pyfile
    def code_to_debug():
        from debug_me import backchannel
        import ptvsd

        ptvsd.break_into_debugger()
        backchannel.write_json("done")

    with debug.Session() as session:
        session.initialize(
            target=(run_as, code_to_debug),
            start_method=start_method,
            debug_options=["WaitOnAbnormalExit"],
            use_backchannel=True,
        )
        session.start_debugging()

        session.wait_for_thread_stopped()
        session.send_request("continue").wait_for_response(freeze=False)

        session.wait_for_termination()

        assert session.read_json() == "done"

        session.wait_for_exit()
