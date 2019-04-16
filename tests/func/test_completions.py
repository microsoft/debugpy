# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

import pytest
from tests.helpers.pattern import ANY
from tests.helpers.session import DebugSession
from tests.helpers.timeline import Event
from ptvsd.messaging import RequestFailure
from tests.helpers import get_marked_line_numbers

expected_at_line = {
    'in_do_something': [
        {'label': 'SomeClass', 'type': 'class', 'start': 0, 'length': 4},
        {'label': 'someFunction', 'type': 'function', 'start': 0, 'length': 4},
        {'label': 'someVariable', 'type': 'field', 'start': 0, 'length': 4},
    ],
    'in_some_function': [
        {'label': 'SomeClass', 'type': 'class', 'start': 0, 'length': 4},
        {'label': 'someFunction', 'type': 'function', 'start': 0, 'length': 4},
        {'label': 'someVar', 'type': 'field', 'start': 0, 'length': 4},
        {'label': 'someVariable', 'type': 'field', 'start': 0, 'length': 4},
    ],
    'done': [
        {'label': 'SomeClass', 'type': 'class', 'start': 0, 'length': 4},
        {'label': 'someFunction', 'type': 'function', 'start': 0, 'length': 4},
    ],
}


@pytest.mark.parametrize('bp_line', sorted(expected_at_line.keys()))
def test_completions_scope(pyfile, bp_line, run_as, start_method):

    @pyfile
    def code_to_debug():
        from dbgimporter import import_and_enable_debugger
        import_and_enable_debugger()

        class SomeClass():

            def __init__(self, someVar):
                self.some_var = someVar

            def do_someting(self):
                someVariable = self.some_var
                return someVariable  # @in_do_something

        def someFunction(someVar):
            someVariable = someVar
            return SomeClass(someVariable).do_someting()  # @in_some_function

        someFunction('value')
        print('done')  # @done

    expected = expected_at_line[bp_line]

    with DebugSession() as session:
        session.initialize(
            target=(run_as, code_to_debug),
            start_method=start_method,
            ignore_unobserved=[Event('stopped')],
        )

        line_numbers = get_marked_line_numbers(code_to_debug)
        session.set_breakpoints(code_to_debug, [line_numbers[bp_line]])
        session.start_debugging()

        thread_stopped = session.wait_for_next(Event('stopped', ANY.dict_with({'reason': 'breakpoint'})))
        assert thread_stopped.body['threadId'] is not None
        tid = thread_stopped.body['threadId']

        resp_stacktrace = session.send_request('stackTrace', arguments={
            'threadId': tid,
        }).wait_for_response()
        assert resp_stacktrace.body['totalFrames'] > 0
        frames = resp_stacktrace.body['stackFrames']
        assert len(frames) > 0

        fid = frames[0]['id']
        resp_completions = session.send_request('completions', arguments={
            'text': 'some',
            'frameId': fid,
            'column': 5,
        }).wait_for_response()
        targets = resp_completions.body['targets']

        session.send_request('continue').wait_for_response(freeze=False)

        targets.sort(key=lambda t: t['label'])
        expected.sort(key=lambda t: t['label'])
        assert targets == expected

        session.wait_for_exit()


def test_completions_cases(pyfile, run_as, start_method):

    @pyfile
    def code_to_debug():
        from dbgimporter import import_and_enable_debugger
        import_and_enable_debugger()
        a = 1
        b = {"one": 1, "two": 2}
        c = 3
        print([a, b, c])  # @break

    line_numbers = get_marked_line_numbers(code_to_debug)
    bp_line = line_numbers['break']
    bp_file = code_to_debug

    with DebugSession() as session:
        session.initialize(
            target=(run_as, bp_file),
            start_method=start_method,
        )
        session.set_breakpoints(bp_file, [bp_line])
        session.start_debugging()
        hit = session.wait_for_thread_stopped()

        response = session.send_request('completions', arguments={
            'frameId': hit.frame_id,
            'text': 'b.',
            'column': 3,
        }).wait_for_response()

        labels = set(target['label'] for target in response.body['targets'])
        assert labels.issuperset(['get', 'items', 'keys', 'setdefault', 'update', 'values'])

        response = session.send_request('completions', arguments={
            'frameId': hit.frame_id,
            'text': 'x = b.setdefault',
            'column': 13,
        }).wait_for_response()

        assert response.body['targets'] == [
            {'label': 'setdefault', 'length': 6, 'start': 6, 'type': 'function'}]

        response = session.send_request('completions', arguments={
            'frameId': hit.frame_id,
            'text': 'not_there',
            'column': 10,
        }).wait_for_response()

        assert not response.body['targets']

        # Check errors
        with pytest.raises(RequestFailure) as request_failure:
            response = session.send_request('completions', arguments={
                'frameId': 9999999,  # frameId not available.
                'text': 'not_there',
                'column': 10,
            }).wait_for_response()
        assert 'Wrong ID sent from the client:' in request_failure.value.message

        session.send_request('continue').wait_for_response(freeze=False)
        session.wait_for_exit()
