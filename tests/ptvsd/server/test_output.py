# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import pytest

from tests import debug


def test_with_no_output(pyfile, start_method, run_as):
    @pyfile
    def code_to_debug():
        import debug_me  # noqa

        # Do nothing, and check if there is any output

    with debug.Session() as session:
        session.initialize(target=(run_as, code_to_debug), start_method=start_method)
        session.start_debugging()
        session.wait_for_exit()

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
        # Break here so we are sure to get the output event.
        a = 1  # @bp1

    with debug.Session() as session:
        session.initialize(target=(run_as, code_to_debug), start_method=start_method)

        session.set_breakpoints(code_to_debug, [code_to_debug.lines["bp1"]])
        session.start_debugging()

        # Breakpoint at the end just to make sure we get all output events.
        session.wait_for_stop()
        session.request_continue()
        session.wait_for_exit()

        assert session.output("stdout").startswith("Hello\tWorld")


@pytest.mark.parametrize("redirect", ["RedirectOutput", ""])
def test_redirect_output(pyfile, start_method, run_as, redirect):
    @pyfile
    def code_to_debug():
        import debug_me  # noqa

        for i in [111, 222, 333, 444]:
            print(i)

        print()  # @bp1

    with debug.Session() as session:
        # By default 'RedirectOutput' is always set. So using this way
        #  to override the default in session.
        session.debug_options = [redirect] if bool(redirect) else []
        session.initialize(target=(run_as, code_to_debug), start_method=start_method)

        session.set_breakpoints(code_to_debug, [code_to_debug.lines["bp1"]])
        session.start_debugging()

        # Breakpoint at the end just to make sure we get all output events.
        session.wait_for_stop()
        session.request_continue()
        session.wait_for_exit()

        if redirect:
            assert session.output("stdout") == "111\n222\n333\n444\n\n"
        else:
            assert not session.output("stdout")
