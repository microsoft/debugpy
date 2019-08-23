# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

from os import path
import pytest
import re

import ptvsd
from ptvsd.common import messaging
from tests import debug, test_data, start_methods
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
        backchannel.wait_for("continue")
        backchannel.send(path.abspath(sys.modules["ptvsd"].__file__))
        print("end")

    with debug.Session(start_method, backchannel=True) as session:
        backchannel = session.backchannel
        session.configure(run_as, code_to_debug)
        session.start_debugging()

        session.timeline.freeze()
        process_event, = session.all_occurrences_of(Event("process"))
        expected_name = (
            "-c"
            if run_as == "code"
            else some.str.matching(re.escape(code_to_debug.strpath) + r"(c|o)?")
        )
        assert process_event == Event(
            "process", some.dict.containing({"name": expected_name})
        )

        backchannel.send("continue")

        expected_ptvsd_path = path.abspath(ptvsd.__file__)
        backchannel.expect(
            some.str.matching(re.escape(expected_ptvsd_path) + r"(c|o)?")
        )

        session.stop_debugging()


def test_run_submodule():
    with debug.Session("launch") as session:
        session.configure("module", "pkg1.sub", cwd=test_data / "testpkgs")
        session.start_debugging()
        session.wait_for_next(
            Event(
                "output",
                some.dict.containing({"category": "stdout", "output": "three"}),
            )
        )
        session.stop_debugging()


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

        with pytest.raises(messaging.InvalidMessageError):
            session.set_breakpoints(code_to_debug, all)

        session.start_debugging()
        backchannel.send(None)

        # Breakpoint shouldn't be hit.
        session.stop_debugging()

        session.expect_realized(
            Event(
                "output", some.dict.containing({"category": "stdout", "output": "ok"})
            )
        )


@pytest.mark.parametrize("run_as", ["script", "module"])
def test_run_vs(pyfile, run_as):
    @pyfile
    def code_to_debug():
        from debug_me import backchannel

        print("ok")
        backchannel.send("ok")

    @pyfile
    def ptvsd_launcher():
        from debug_me import backchannel
        import ptvsd.debugger

        args = tuple(backchannel.receive())
        ptvsd.debugger.debug(*args)

    filename = "code_to_debug" if run_as == "module" else code_to_debug
    with debug.Session("custom_client", backchannel=True) as session:
        backchannel = session.backchannel

        @session.before_connect
        def before_connect():
            backchannel.send([filename, session.ptvsd_port, None, None, run_as])

        session.configure("program", ptvsd_launcher)
        session.start_debugging()

        assert backchannel.receive() == "ok"
        session.stop_debugging()
