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
from pytests.helpers.pattern import ANY


BP_TEST_ROOT = get_test_root('bp')


def test_path_with_ampersand(run_as, start_method):
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
def test_path_with_unicode(run_as, start_method):
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


@pytest.mark.parametrize('condition_key', [
    'condition_var',
    'hitCondition_#',
    'hitCondition_eq',
    'hitCondition_gt',
    'hitCondition_ge',
    'hitCondition_lt',
    'hitCondition_le',
    'hitCondition_mod',
])
def test_conditional_breakpoint(pyfile, run_as, start_method, condition_key):
    @pyfile
    def code_to_debug():
        from dbgimporter import import_and_enable_debugger
        import_and_enable_debugger()
        for i in range(0, 10):
            print(i)

    expected = {
        'condition_var': ('condition', 'i==5', '5', 1),
        'hitCondition_#': ('hitCondition', '5', '4', 1),
        'hitCondition_eq': ('hitCondition', '==5', '4', 1),
        'hitCondition_gt': ('hitCondition', '>5', '5', 5),
        'hitCondition_ge': ('hitCondition', '>=5', '4', 6),
        'hitCondition_lt': ('hitCondition', '<5', '0', 4),
        'hitCondition_le': ('hitCondition', '<=5', '0', 5),
        'hitCondition_mod': ('hitCondition', '%3', '2', 3),
    }
    condition_type, condition, value, hits = expected[condition_key]

    bp_line = 4
    with DebugSession() as session:
        session.initialize(
            target=(run_as, code_to_debug),
            start_method=start_method,
            ignore_unobserved=[Event('continued')],
        )
        session.send_request('setBreakpoints', arguments={
            'source': {'path': code_to_debug},
            'breakpoints': [{'line': bp_line, condition_type: condition}],
        }).wait_for_response()
        session.start_debugging()
        hit = session.wait_for_thread_stopped()
        frames = hit.stacktrace.body['stackFrames']
        assert bp_line == frames[0]['line']

        resp_scopes = session.send_request('scopes', arguments={
            'frameId': hit.frame_id
        }).wait_for_response()
        scopes = resp_scopes.body['scopes']
        assert len(scopes) > 0

        resp_variables = session.send_request('variables', arguments={
            'variablesReference': scopes[0]['variablesReference']
        }).wait_for_response()
        variables = list(v for v in resp_variables.body['variables']
                         if v['name'] == 'i')
        assert variables == [
            ANY.dict_with({'name': 'i', 'type': 'int', 'value': value, 'evaluateName': 'i'})
        ]

        session.send_request('continue').wait_for_response(freeze=False)
        for i in range(1, hits):
            session.wait_for_thread_stopped()
            session.send_request('continue').wait_for_response(freeze=False)
        session.wait_for_exit()
