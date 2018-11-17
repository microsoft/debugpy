# -*- coding: utf-8 -*-
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

import os.path
import pytest
import sys

from pytests.helpers.pathutils import get_test_root, compare_path
from pytests.helpers.session import DebugSession
from pytests.helpers.timeline import Event


BP_TEST_ROOT = get_test_root('bp')


def test_path_with_ampersand(start_method, run_as):
    bp_line = 4
    testfile = os.path.join(BP_TEST_ROOT, 'a&b', 'test.py')

    with DebugSession() as session:
        session.initialize(
            target=(run_as, testfile),
            start_method=start_method,
            ignore_unobserved=[Event('continued')],
        )
        session.set_breakpoints(testfile, [bp_line])
        session.start_debugging()
        hit = session.wait_for_thread_stopped('breakpoint')
        frames = hit.stacktrace.body['stackFrames']
        assert compare_path(frames[0]['source']['path'], testfile, show=False)

        session.send_request('continue').wait_for_response(freeze=False)
        session.wait_for_exit()


@pytest.mark.skipif(sys.version_info < (3, 0), reason='Paths are not Unicode in Python 2.7')
def test_path_with_unicode(start_method, run_as):
    bp_line = 6
    testfile = os.path.join(BP_TEST_ROOT, u'ನನ್ನ_ಸ್ಕ್ರಿಪ್ಟ್.py')

    with DebugSession() as session:
        session.initialize(
            target=(run_as, testfile),
            start_method=start_method,
            ignore_unobserved=[Event('continued')],
        )
        session.set_breakpoints(testfile, [bp_line])
        session.start_debugging()
        hit = session.wait_for_thread_stopped('breakpoint')
        frames = hit.stacktrace.body['stackFrames']
        assert compare_path(frames[0]['source']['path'], testfile, show=False)
        assert u'ಏನಾದರೂ_ಮಾಡು' == frames[0]['name']

        session.send_request('continue').wait_for_response(freeze=False)
        session.wait_for_exit()
