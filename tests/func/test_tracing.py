# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

from tests.helpers import get_marked_line_numbers, print
from tests.helpers.session import DebugSession
from tests.helpers.timeline import Event
from tests.helpers.pattern import ANY


def test_tracing(pyfile, start_method, run_as):
    @pyfile
    def code_to_debug():
        from dbgimporter import import_and_enable_debugger
        import_and_enable_debugger()

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

    line_numbers = get_marked_line_numbers(code_to_debug)
    print(line_numbers)

    with DebugSession() as session:
        session.initialize(
            target=(run_as, code_to_debug),
            start_method=start_method,
            ignore_unobserved=[Event('continued')],
            env={'PTVSD_USE_CONTINUED': '1'},
        )

        session.set_breakpoints(code_to_debug, line_numbers.values())
        session.start_debugging()

        stop = session.wait_for_thread_stopped()
        frame = stop.stacktrace.body['stackFrames'][0]
        assert frame == ANY.dict_with({
            "line": line_numbers["inner2"],
        })

        session.send_request('continue').wait_for_response()

        stop = session.wait_for_thread_stopped()
        frame = stop.stacktrace.body['stackFrames'][0]
        assert frame == ANY.dict_with({
            "line": line_numbers["outer2"],
        })

        session.send_request('continue').wait_for_response()

        stop = session.wait_for_thread_stopped()
        frame = stop.stacktrace.body['stackFrames'][0]
        assert frame == ANY.dict_with({
            "line": line_numbers["inner1"],
        })

        session.send_request('continue').wait_for_response()

        stop = session.wait_for_thread_stopped()
        frame = stop.stacktrace.body['stackFrames'][0]
        assert frame == ANY.dict_with({
            "line": line_numbers["inner3"],
        })

        session.send_request('continue').wait_for_response()
        session.wait_for_exit()
