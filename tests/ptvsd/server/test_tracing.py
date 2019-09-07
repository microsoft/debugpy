# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

from tests import debug
from tests.printer import print
from tests.patterns import some


def test_tracing(pyfile, start_method, run_as):

    @pyfile
    def code_to_debug():
        import debug_me # noqa

        import ptvsd

        def func(expected_tracing):
            assert ptvsd.tracing() == expected_tracing, (
                "inside func({0!r})".format(expected_tracing)
            )
            print(1)  # @inner1

            # Test nested change/restore. Going from False to True only works entirely
            # correctly on Python 3.6+; on earlier versions, if tracing wasn't enabled
            # when the function is entered, re-enabling it later will not cause the
            # breakpoints in this function to light up. However, it will allow hitting
            # breakpoints in functions called from here.

            def inner2():
                print(2)  # @inner2

            with ptvsd.tracing(not expected_tracing):
                assert ptvsd.tracing() != expected_tracing, "inside with-statement"
                inner2()
            assert ptvsd.tracing() == expected_tracing, "after with-statement"

            print(3)  # @inner3

        assert ptvsd.tracing(), "before tracing(False)"
        ptvsd.tracing(False)
        assert not ptvsd.tracing(), "after tracing(False)"

        print(0)  # @outer1
        func(False)

        ptvsd.tracing(True)
        assert ptvsd.tracing(), "after tracing(True)"

        print(0)  # @outer2
        func(True)

    print(code_to_debug.lines)
    with debug.Session(start_method, client_id='vscode') as session:
        session.configure(run_as, code_to_debug)
        session.set_breakpoints(code_to_debug, all)
        session.start_debugging()

        stop = session.wait_for_stop()
        frame = stop.frames[0]
        assert frame == some.dict.containing({
            "line": code_to_debug.lines["inner2"],
        })

        session.request_continue()

        stop = session.wait_for_stop()
        frame = stop.frames[0]
        assert frame == some.dict.containing({
            "line": code_to_debug.lines["outer2"],
        })

        session.request_continue()

        stop = session.wait_for_stop()
        frame = stop.frames[0]
        assert frame == some.dict.containing({
            "line": code_to_debug.lines["inner1"],
        })

        session.request_continue()

        stop = session.wait_for_stop()
        frame = stop.frames[0]
        assert frame == some.dict.containing({
            "line": code_to_debug.lines["inner3"],
        })

        session.request_continue()
