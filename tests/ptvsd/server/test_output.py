# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import pytest

from tests import debug
from tests.patterns import some
from tests.timeline import Event


def test_with_no_output(pyfile, start_method, run_as):

    @pyfile
    def code_to_debug():
        from dbgimporter import import_and_enable_debugger
        import_and_enable_debugger()
        # Do nothing, and check if there is any output

    with debug.Session() as session:
        session.initialize(target=(run_as, code_to_debug), start_method=start_method)
        session.start_debugging()
        session.wait_for_exit()
        assert b'' == session.get_stdout_as_string()
        assert b'' == session.get_stderr_as_string()


def test_with_tab_in_output(pyfile, start_method, run_as):

    @pyfile
    def code_to_debug():
        from dbgimporter import import_and_enable_debugger
        import_and_enable_debugger()
        a = '\t'.join(('Hello', 'World'))
        print(a)
        # Break here so we are sure to get the output event.
        a = 1  # @bp1

    line_numbers = get_marked_line_numbers(code_to_debug)
    with debug.Session() as session:
        session.initialize(
            target=(run_as, code_to_debug),
            start_method=start_method,
        )

        session.set_breakpoints(code_to_debug, [line_numbers['bp1']])
        session.start_debugging()

        # Breakpoint at the end just to make sure we get all output events.
        session.wait_for_thread_stopped()
        session.send_request('continue').wait_for_response(freeze=False)
        session.wait_for_exit()

        output = session.all_occurrences_of(Event('output', ANY.dict_with({'category': 'stdout'})))
        output_str = ''.join(o.body['output'] for o in output)
        assert output_str.startswith('Hello\tWorld')


@pytest.mark.parametrize('redirect', ['RedirectOutput', ''])
def test_redirect_output(pyfile, start_method, run_as, redirect):
    @pyfile
    def code_to_debug():
        from dbgimporter import import_and_enable_debugger
        import_and_enable_debugger()

        for i in [111, 222, 333, 444]:
            print(i)

        print() # @bp1

    line_numbers = get_marked_line_numbers(code_to_debug)
    with debug.Session() as session:
        # By default 'RedirectOutput' is always set. So using this way
        #  to override the default in session.
        session.debug_options = [redirect] if bool(redirect) else []
        session.initialize(
            target=(run_as, code_to_debug),
            start_method=start_method,
        )

        session.set_breakpoints(code_to_debug, [line_numbers['bp1']])
        session.start_debugging()

        # Breakpoint at the end just to make sure we get all output events.
        session.wait_for_thread_stopped()
        session.send_request('continue').wait_for_response(freeze=False)
        session.wait_for_exit()

        output = session.all_occurrences_of(Event('output', ANY.dict_with({'category': 'stdout'})))
        expected = ['111', '222', '333', '444'] if bool(redirect) else []
        assert expected == list(o.body['output'] for o in output if len(o.body['output']) == 3)
