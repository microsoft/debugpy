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

    with debug.Session() as session:
        session.initialize(
            target=(run_as, code_to_debug),
            start_method=start_method,
            ignore_unobserved=[Event("stopped")],
        )
        session.set_breakpoints(test_module, [code_to_debug.lines["bp"]])
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
            frames[0]["name"].find(": " + str(code_to_debug.lines["bp"])) > -1
        )

        assert module == (frames[0]["name"].find("test_module") > -1)

        session.send_continue()
        session.wait_for_exit()


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

    with debug.Session() as session:
        session.initialize(
            target=(run_as, test_code),
            start_method=start_method,
            ignore_unobserved=[Event("stopped")],
        )
        session.set_breakpoints(module2, [module2.lines["bp"]])
        session.start_debugging()

        session.wait_for_stop()
        modules = session.all_occurrences_of(Event("module"))
        modules = [
            (m.body["module"]["name"], m.body["module"]["path"]) for m in modules
        ]
        assert modules[:3] == [
            ("module2", some.path(module2)),
            ("module1", some.path(module1)),
            ("__main__", some.path(test_code)),
        ]

        session.send_continue()
        session.wait_for_exit()
