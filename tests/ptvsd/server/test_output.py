# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import pytest

from tests import debug


# When debuggee exits, there's no guarantee currently that all "output" events have
# already been sent. To ensure that they are, all tests below must set a breakpoint
# on the last line of the debuggee, and stop on it. Since debugger sends its events
# sequentially, by the time we get to "stopped", we also have all the output events.


def test_with_no_output(pyfile, start_method, run_as):
    @pyfile
    def code_to_debug():
        import debug_me  # noqa
        ()  # @wait_for_output

    with debug.Session(start_method) as session:
        session.configure(run_as, code_to_debug)
        session.set_breakpoints(code_to_debug, all)

        session.start_debugging()
        session.wait_for_stop("breakpoint")
        session.request_continue()
        session.stop_debugging()

        assert not session.output("stdout")
        assert not session.output("stderr")
        assert not session.captured_stdout()
        assert not session.captured_stderr()


def test_with_tab_in_output(pyfile, start_method, run_as):
    @pyfile
    def code_to_debug():
        import debug_me  # noqa

        a = "\t".join(("Hello", "World"))
        print(a)
        ()  # @wait_for_output

    with debug.Session(start_method) as session:
        session.configure(run_as, code_to_debug)

        session.set_breakpoints(code_to_debug, all)
        session.start_debugging()
        session.wait_for_stop()
        session.request_continue()
        session.stop_debugging()

        assert session.output("stdout").startswith("Hello\tWorld")


@pytest.mark.parametrize("redirect", ["enabled", "disabled"])
def test_redirect_output(pyfile, start_method, run_as, redirect):
    @pyfile
    def code_to_debug():
        import debug_me  # noqa

        for i in [111, 222, 333, 444]:
            print(i)

        ()  # @wait_for_output

    with debug.Session(start_method) as session:
        if redirect == "disabled":
            session.debug_options -= {"RedirectOutput"}  # enabled by default
        session.configure(run_as, code_to_debug)
        session.set_breakpoints(code_to_debug, all)
        session.start_debugging()

        session.wait_for_stop()
        session.request_continue()
        session.stop_debugging()

        if redirect == "enabled":
            assert session.output("stdout") == "111\n222\n333\n444\n"
        else:
            assert not session.output("stdout")
