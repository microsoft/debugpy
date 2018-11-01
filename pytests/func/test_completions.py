# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

import pytest
from ..helpers.pattern import ANY
from ..helpers.timeline import Event


def run_test_completion(debug_session, pyfile, bp_line, expected):
    @pyfile
    def code_to_debug():
        class SomeClass():
            def __init__(self, someVar):
                self.some_var = someVar
            def do_someting(self):
                someVariable = self.some_var
                return someVariable
        def someFunction(someVar):
            someVariable = someVar
            return SomeClass(someVariable).do_someting()
        someFunction('value')
        print('done')

    debug_session.multiprocess = False
    debug_session.ignore_unobserved += [
        Event('thread', ANY.dict_with({'reason': 'started'})),
        Event('module'),
        Event('stopped'),
        Event('continued')
    ]
    debug_session.prepare_to_run(filename=code_to_debug)
    debug_session.send_request('setBreakpoints', arguments={
        'source': {'path': code_to_debug},
        'breakpoints': [{'line': bp_line}, ],
    }).wait_for_response()

    debug_session.start_debugging()

    thread_stopped = debug_session.wait_for_next(Event('stopped'), ANY.dict_with({'reason': 'breakpoint'}))
    assert thread_stopped.body['threadId'] is not None
    tid = thread_stopped.body['threadId']

    resp_stacktrace = debug_session.send_request('stackTrace', arguments={
        'threadId': tid,
    }).wait_for_response()
    assert resp_stacktrace.body['totalFrames'] > 0
    frames = resp_stacktrace.body['stackFrames']
    assert len(frames) > 0

    fid = frames[0]['id']
    resp_completions = debug_session.send_request('completions', arguments={
        'text': 'some',
        'frameId': fid,
        'column': 1
    }).wait_for_response()
    targets = resp_completions.body['targets']

    debug_session.send_request('continue').wait_for_response()

    targets.sort(key=lambda t: t['label'])
    expected.sort(key=lambda t: t['label'])
    assert targets == expected

    debug_session.wait_for_exit()


expected_at_line = {
    6: [
        {'label': 'SomeClass', 'type': 'class'},
        {'label': 'someFunction', 'type': 'function'},
        {'label': 'someVariable', 'type': 'field'},
    ],
    9: [
        {'label': 'SomeClass', 'type': 'class'},
        {'label': 'someFunction', 'type': 'function'},
        {'label': 'someVar', 'type': 'field'},
        {'label': 'someVariable', 'type': 'field'},
    ],
    11: [
        {'label': 'SomeClass', 'type': 'class'},
        {'label': 'someFunction', 'type': 'function'},
    ],
}

@pytest.mark.parametrize('bp_line', expected_at_line.keys())
def test_completions_scope(debug_session, pyfile, bp_line):
    run_test_completion(debug_session, pyfile, bp_line, expected_at_line[bp_line])

def test_completions(debug_session, simple_hit_paused_on_break):
    hit = simple_hit_paused_on_break

    response = debug_session.send_request('completions', arguments={
        'frameId': hit.frame_id,
        'text': 'b.'
    }).wait_for_response()

    labels = set(target['label'] for target in response.body['targets'])
    assert labels.issuperset(['get', 'items', 'keys', 'setdefault', 'update', 'values'])

    response = debug_session.send_request('completions', arguments={
        'frameId': hit.frame_id,
        'text': 'not_there'
    }).wait_for_response()

    assert not response.body['targets']
