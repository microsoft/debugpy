# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

from os import path
import pytest
import re

import ptvsd
from ptvsd.common import messaging
from tests import debug, test_data
from tests.debug import start_methods
from tests.patterns import some
from tests.timeline import Event


@pytest.mark.parametrize("run_as", ["program", "module", "code"])
def test_run(pyfile, start_method, run_as):
    @pyfile
    def code_to_debug():
        from debug_me import backchannel
        from os import path
        import sys

        print("begin")
        backchannel.send(path.abspath(sys.modules["ptvsd"].__file__))
        backchannel.wait_for("continue")
        print("end")

    with debug.Session(start_method, backchannel=True) as session:
        backchannel = session.backchannel
        session.configure(run_as, code_to_debug)
        session.start_debugging()

        expected_ptvsd_path = path.abspath(ptvsd.__file__)
        backchannel.expect(
            some.str.matching(re.escape(expected_ptvsd_path) + r"(c|o)?")
        )

        backchannel.send("continue")
        session.wait_for_next_event("terminated")
        session.proceed()


def test_run_submodule():
    with debug.Session(start_methods.Launch, backchannel=True) as session:
        session.configure("module", "pkg1.sub", cwd=test_data / "testpkgs")
        session.start_debugging()
        session.backchannel.expect("ok")


@pytest.mark.parametrize("run_as", ["program", "module", "code"])
def test_nodebug(pyfile, run_as):
    @pyfile
    def code_to_debug():
        from debug_me import backchannel

        backchannel.receive()  # @ bp1
        print("ok")  # @ bp2

    with debug.Session(start_methods.Launch, backchannel=True) as session:
        backchannel = session.backchannel
        session.configure(
            run_as, code_to_debug, noDebug=True, console="internalConsole"
        )

        with pytest.raises(messaging.MessageHandlingError):
            session.set_breakpoints(code_to_debug, all)

        session.start_debugging()
        backchannel.send(None)

        # Breakpoint shouldn't be hit.

    session.expect_realized(
        Event("output", some.dict.containing({"category": "stdout", "output": "ok"}))
    )
