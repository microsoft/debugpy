# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

import os.path
from pytests.helpers.timeline import Event
from ..helpers.pathutils import get_test_root, compare_path

BP_TEST_ROOT = get_test_root('bp')


def test_path_with_ampersand(debug_session):
    bp_line = 2
    testfile = os.path.join(BP_TEST_ROOT, 'a&b', 'test.py')
    debug_session.common_setup(testfile, 'file', [bp_line])
    debug_session.start_debugging()
    hit = debug_session.wait_for_thread_stopped()
    frames = hit.stacktrace.body['stackFrames']
    assert compare_path(frames[0]['source']['path'], testfile)

    debug_session.send_request('continue').wait_for_response()
    debug_session.wait_for_next(Event('continued'))

    debug_session.wait_for_exit()
