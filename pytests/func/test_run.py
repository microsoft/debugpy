# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

import os
import ptvsd

from ..helpers.pattern import ANY
from ..helpers.timeline import Event


def test_run(debug_session, pyfile):
    @pyfile
    def code_to_debug():
        import os
        import sys
        from pytests.helpers import backchannel

        print('begin')
        assert backchannel.read_json() == 'continue'
        backchannel.write_json(os.path.abspath(sys.modules['ptvsd'].__file__))
        print('end')

    debug_session.prepare_to_run(filename=code_to_debug, backchannel=True)
    debug_session.start_debugging()
    assert debug_session.timeline.is_frozen

    process_event, = debug_session.all_occurrences_of(Event('process'))
    assert process_event == Event('process', ANY.dict_with({
        'name': code_to_debug,
    }))

    debug_session.write_json('continue')
    ptvsd_path = debug_session.read_json()
    assert ptvsd_path == os.path.abspath(ptvsd.__file__)

    debug_session.wait_for_exit()
