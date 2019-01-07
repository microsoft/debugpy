# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import
from tests.helpers.session import DebugSession
from tests.helpers.timeline import Event
from tests.helpers.pattern import ANY


def test_with_no_output(pyfile, run_as, start_method):
    @pyfile
    def code_to_debug():
        from dbgimporter import import_and_enable_debugger
        import_and_enable_debugger()
        # Do nothing, and check if there is any output

    with DebugSession() as session:
        session.initialize(target=(run_as, code_to_debug), start_method=start_method)
        session.start_debugging()
        session.wait_for_exit()
        assert b'' == session.get_stdout_as_string()
        assert b'' == session.get_stderr_as_string()


def test_with_tab_in_output(pyfile, run_as, start_method):
    @pyfile
    def code_to_debug():
        from dbgimporter import import_and_enable_debugger
        import_and_enable_debugger()
        print('Hello\tWorld')

    with DebugSession() as session:
        session.initialize(target=(run_as, code_to_debug), start_method=start_method)
        session.start_debugging()
        session.wait_for_exit()
        output = session.all_occurrences_of(Event('output', ANY.dict_with({'category': 'stdout'})))
        output_str = ''.join(o.body['output'] for o in output)
        assert output_str.startswith('Hello\tWorld')
