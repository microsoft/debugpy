# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import pytest

from tests import debug
from tests.patterns import some
from tests.timeline import Event


@pytest.mark.parametrize("module", ["module", ""])
@pytest.mark.parametrize("line", ["line", ""])
def test_stack_format(pyfile, target, run, module, line):
    @pyfile
    def code_to_debug():
        import debuggee
        from test_module import do_something

        debuggee.setup()
        do_something()

    @pyfile
    def test_module():
        def do_something():
            print("break here")  # @bp

    with debug.Session() as session:
        with run(session, target(code_to_debug)):
            session.set_breakpoints(test_module, all)

        stop = session.wait_for_stop(
            "breakpoint", expected_frames=[some.dap.frame(test_module, line="bp")]
        )
        stack_trace = session.request(
            "stackTrace",
            {
                "threadId": stop.thread_id,
                "format": {"module": bool(module), "line": bool(line)},
            },
        )
        assert stack_trace["totalFrames"] > 0
        name = stack_trace["stackFrames"][0]["name"]
        if line:
            assert (": " + str(test_module.lines["bp"])) in name
        if module:
            assert "test_module" in name
        session.request_continue()


def test_module_events(pyfile, target, run):
    @pyfile
    def module2():
        def do_more_things():
            print("done")  # @bp

    @pyfile
    def module1():
        import module2

        def do_something():
            module2.do_more_things()

    @pyfile
    def test_code():
        import debuggee

        debuggee.setup()

        from module1 import do_something

        do_something()

    with debug.Session() as session:
        with run(session, target(test_code)):
            session.set_breakpoints(module2, all)

        session.wait_for_stop(
            "breakpoint", expected_frames=[some.dap.frame(module2, line="bp")]
        )

        # Stack trace after the stop will trigger module events, but they are only
        # sent after the trace response, so we need to wait for them separately.
        # The order isn't guaranteed, either, so just wait for any 3 modules.
        session.timeline.wait_until_realized(
            Event("module") >> Event("module") >> Event("module")
        )
        modules = {
            event.body["module"]["name"]: event.body["module"]["path"]
            for event in session.all_occurrences_of(Event("module"))
        }
        assert modules == some.dict.containing(
            {
                "__main__": some.path(test_code),
                "module1": some.path(module1),
                "module2": some.path(module2),
            }
        )

        session.request_continue()
