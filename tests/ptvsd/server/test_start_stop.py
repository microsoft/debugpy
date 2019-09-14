# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import platform
import pytest
import sys
import time

from ptvsd.common import log
from tests import debug
from tests.debug import runners
from tests.patterns import some


def has_waited(session):
    lines = session.captured_output.stdout_lines()
    result = any(
        s == some.bytes.matching(br"Press .* to continue . . .\s*") for s in lines
    )
    # log.info("!!! {1} {0!r}", lines, result)
    return result


def wait_and_press_key(session):
    log.info("Waiting for keypress prompt...")
    while not has_waited(session):
        time.sleep(0.1)
    log.info("Simulating keypress.")
    session.process.stdin.write(b" \r\n")


@pytest.mark.skipif(
    sys.version_info < (3, 0) and platform.system() == "Windows",
    reason="On Windows + Python 2, unable to send key strokes to test.",
)
def test_wait_on_normal_exit_enabled(pyfile, run_as):
    @pyfile
    def code_to_debug():
        from debug_me import ptvsd

        ptvsd.break_into_debugger()
        print()  # line on which it'll actually break

    with debug.Session(runners.launch) as session:
        session.configure(run_as, code_to_debug, waitOnNormalExit=True)
        session.start_debugging()

        session.wait_for_stop()
        session.request_continue()

        wait_and_press_key(session)


@pytest.mark.skipif(
    sys.version_info < (3, 0) and platform.system() == "Windows",
    reason="On Windows + Python 2, unable to send key strokes to test.",
)
def test_wait_on_abnormal_exit_enabled(pyfile, run_as):
    @pyfile
    def code_to_debug():
        from debug_me import ptvsd
        import sys

        ptvsd.break_into_debugger()
        print()  # line on which it'll actually break
        sys.exit(42)

    with debug.Session(runners.launch) as session:
        session.expected_exit_code = 42
        session.configure(run_as, code_to_debug, waitOnAbnormalExit=True)
        session.start_debugging()

        session.wait_for_stop()
        session.request_continue()

        wait_and_press_key(session)


def test_exit_normally_with_wait_on_abnormal_exit_enabled(pyfile, run_as):
    @pyfile
    def code_to_debug():
        from debug_me import ptvsd

        ptvsd.break_into_debugger()
        print()

    with debug.Session(runners.launch) as session:
        session.configure(run_as, code_to_debug, waitOnAbnormalExit=True)
        session.start_debugging()

        session.wait_for_stop()
        session.request_continue()

        session.wait_for_next_event("exited")
        assert not has_waited(session)
        session.proceed()
