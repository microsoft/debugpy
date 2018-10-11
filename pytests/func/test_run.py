# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

import os
import pytest

import ptvsd

from pytests.helpers import print
from pytests.helpers.pattern import ANY
from pytests.helpers.timeline import Event


@pytest.mark.parametrize('run_as', ['file', 'module', 'code'])
def test_run(debug_session, pyfile, run_as):
    @pyfile
    def code_to_debug():
        import os
        import sys
        from pytests.helpers import backchannel

        print('begin')
        assert backchannel.read_json() == 'continue'
        backchannel.write_json(os.path.abspath(sys.modules['ptvsd'].__file__))
        print('end')

    if run_as == 'file':
        debug_session.prepare_to_run(filename=code_to_debug, backchannel=True)
    elif run_as == 'module':
        debug_session.add_file_to_pythonpath(code_to_debug)
        debug_session.prepare_to_run(module='code_to_debug', backchannel=True)
    elif run_as == 'code':
        with open(code_to_debug, 'r') as f:
            code = f.read()
        debug_session.prepare_to_run(code=code, backchannel=True)
    else:
        pytest.fail()

    debug_session.start_debugging()
    assert debug_session.timeline.is_frozen

    process_event, = debug_session.all_occurrences_of(Event('process'))
    assert process_event == Event('process', ANY.dict_with({
        'name': ANY if run_as == 'code' else ANY.such_that(lambda name: (
            # There can be a difference in file extension (.py/.pyc/.pyo) on clean runs.
            name == code_to_debug or
            name == code_to_debug + 'c' or
            name == code_to_debug + 'o'
        )),
    }))

    debug_session.write_json('continue')
    ptvsd_path = debug_session.read_json()
    assert ptvsd_path == os.path.abspath(ptvsd.__file__)

    debug_session.wait_for_exit()
