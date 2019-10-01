# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import pytest
import sys
import time

from ptvsd.common import log
from tests import debug
from tests.debug import runners
from tests.patterns import some


def has_waited(session):
    lines = session.captured_output.stdout_lines()
    return any(
        s == some.bytes.matching(br"Press .* to continue . . .\s*") for s in lines
    )


def wait_and_press_key(session):
    log.info("Waiting for keypress prompt...")
    while not has_waited(session):
        time.sleep(0.1)

    # Wait a bit to simulate the user reaction time, and test that debuggee does
    # not exit all by itself.
    time.sleep(1)

    log.info("Simulating keypress.")
    session.debuggee.stdin.write(b"\n")


@pytest.mark.skipif(
    sys.version_info < (3, 0), reason="https://github.com/microsoft/ptvsd/issues/1819"
)
@pytest.mark.parametrize(
    "run", [runners.launch["integratedTerminal"], runners.launch["externalTerminal"]]
)
def test_wait_on_normal_exit_enabled(pyfile, target, run):
    @pyfile
    def code_to_debug():
        from debug_me import ptvsd

        ptvsd.break_into_debugger()
        print()  # line on which it'll actually break

    with debug.Session() as session:
        session.config["waitOnNormalExit"] = True

        with run(session, target(code_to_debug)):
            pass

        session.wait_for_stop()
        session.request_continue()

        wait_and_press_key(session)


@pytest.mark.skipif(
    sys.version_info < (3, 0), reason="https://github.com/microsoft/ptvsd/issues/1819"
)
@pytest.mark.parametrize(
    "run", [runners.launch["integratedTerminal"], runners.launch["externalTerminal"]]
)
def test_wait_on_abnormal_exit_enabled(pyfile, target, run):
    @pyfile
    def code_to_debug():
        from debug_me import ptvsd
        import sys

        ptvsd.break_into_debugger()
        print()  # line on which it'll actually break
        sys.exit(42)

    with debug.Session() as session:
        session.expected_exit_code = 42
        session.config["waitOnAbnormalExit"] = True

        with run(session, target(code_to_debug)):
            pass

        session.wait_for_stop()
        session.request_continue()

        wait_and_press_key(session)


@pytest.mark.parametrize(
    "run", [runners.launch["integratedTerminal"], runners.launch["externalTerminal"]]
)
def test_exit_normally_with_wait_on_abnormal_exit_enabled(pyfile, target, run):
    @pyfile
    def code_to_debug():
        from debug_me import ptvsd

        ptvsd.break_into_debugger()
        print()

    with debug.Session() as session:
        session.config["waitOnAbnormalExit"] = True

        with run(session, target(code_to_debug)):
            pass

        session.wait_for_stop()
        session.request_continue()

        session.wait_for_next_event("exited")
        assert not has_waited(session)
