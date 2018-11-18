# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import
from pytests.helpers.session import DebugSession
import pytest

@pytest.mark.parametrize('run_as', ['file', 'module', 'code'])
def test_args(pyfile, run_as, start_method):
    @pyfile
    def code_to_debug():
        import sys
        from dbgimporter import import_and_enable_debugger
        import_and_enable_debugger()
        assert sys.argv[1] == '--arg1'
        assert sys.argv[2] == 'arg2'
        assert sys.argv[3] == '-arg3'

    args = ['--arg1', 'arg2', '-arg3']
    with DebugSession() as session:
        session.initialize(
            target=(run_as, code_to_debug),
            start_method=start_method,
            program_args=args
        )
        session.start_debugging()

        session.wait_for_exit()
