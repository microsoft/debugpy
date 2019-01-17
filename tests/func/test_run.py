# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

import os
import pytest
import re

import ptvsd

from tests.helpers import print
from tests.helpers.pattern import ANY, Regex
from tests.helpers.session import DebugSession
from tests.helpers.timeline import Event


@pytest.mark.parametrize('run_as', ['file', 'module', 'code'])
def test_run(pyfile, run_as, start_method):
    @pyfile
    def code_to_debug():
        import os
        import sys
        import backchannel
        from dbgimporter import import_and_enable_debugger
        import_and_enable_debugger()

        print('begin')
        assert backchannel.read_json() == 'continue'
        backchannel.write_json(os.path.abspath(sys.modules['ptvsd'].__file__))
        print('end')

    with DebugSession() as session:
        session.initialize(target=(run_as, code_to_debug), start_method=start_method, use_backchannel=True)
        session.start_debugging()
        assert session.timeline.is_frozen

        process_event, = session.all_occurrences_of(Event('process'))
        assert process_event == Event('process', ANY.dict_with({
            'name': '-c' if run_as == 'code' else Regex(re.escape(code_to_debug) + r'(c|o)?$')
        }))

        session.write_json('continue')
        ptvsd_path = session.read_json()
        expected_ptvsd_path = os.path.abspath(ptvsd.__file__)
        assert re.match(re.escape(expected_ptvsd_path) + r'(c|o)?$', ptvsd_path)

        session.wait_for_exit()
