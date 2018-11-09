# -*- coding: utf-8 -*-
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

import os.path
import pytest
from pytests.helpers.timeline import Event
from pytests.helpers.pathutils import get_test_root, compare_path
from pytests.helpers.session import START_METHOD_LAUNCH, START_METHOD_CMDLINE

BP_TEST_ROOT = get_test_root('bp')


@pytest.mark.parametrize('start_method', [START_METHOD_LAUNCH, START_METHOD_CMDLINE])
def test_path_with_ampersand(debug_session, start_method):
    bp_line = 2
    testfile = os.path.join(BP_TEST_ROOT, 'a&b', 'test.py')
    debug_session.initialize(target=('file', testfile), start_method=start_method)
    debug_session.set_breakpoints(testfile, [bp_line])
    debug_session.start_debugging()
    hit = debug_session.wait_for_thread_stopped()
    frames = hit.stacktrace.body['stackFrames']
    assert compare_path(frames[0]['source']['path'], testfile, show=False)

    debug_session.send_request('continue').wait_for_response()
    debug_session.wait_for_next(Event('continued'))

    debug_session.wait_for_exit()
