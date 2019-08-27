# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import pytest

from tests import debug
from tests.patterns import some
from tests.timeline import Event


@pytest.mark.parametrize("module", [True, False])
@pytest.mark.parametrize("line", [True, False])
def test_stack_format(pyfile, start_method, run_as, module, line):
    @pyfile
    def code_to_debug():
        import debug_me  # noqa
        from test_module import do_something

        do_something()

    @pyfile
    def test_module():
        def do_something():
            print("break here")  # @bp

    with debug.Session(start_method) as session:
        session.configure(run_as, code_to_debug)
        session.set_breakpoints(test_module, [test_module.lines["bp"]])
        session.start_debugging()

        hit = session.wait_for_stop()
        resp_stacktrace = session.send_request(
            "stackTrace",
            arguments={
                "threadId": hit.thread_id,
                "format": {"module": module, "line": line},
            },
        ).wait_for_response()
        assert resp_stacktrace.body["totalFrames"] > 0
        frames = resp_stacktrace.body["stackFrames"]

        assert line == (
            frames[0]["name"].find(": " + str(test_module.lines["bp"])) > -1
        )

        assert module == (frames[0]["name"].find("test_module") > -1)

        session.request_continue()


def test_module_events(pyfile, start_method, run_as):
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
        import debug_me  # noqa
        from module1 import do_something

        do_something()

    with debug.Session(start_method) as session:
        session.configure(run_as, test_code)
        session.set_breakpoints(module2, [module2.lines["bp"]])
        session.start_debugging()

        session.wait_for_stop()

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
        assert modules == {
            "__main__": some.path(test_code),
            "module1": some.path(module1),
            "module2": some.path(module2),
        }

        session.request_continue()
