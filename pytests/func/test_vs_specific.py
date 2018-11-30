# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

import pytest
from pytests.helpers.session import DebugSession
from pytests.helpers.timeline import Event
from pytests.helpers.pattern import ANY


@pytest.mark.parametrize('module', [True, False])
@pytest.mark.parametrize('line', [True, False])
def test_stack_format(pyfile, run_as, start_method, module, line):
    @pyfile
    def code_to_debug():
        from dbgimporter import import_and_enable_debugger
        import_and_enable_debugger()
        from test_module import do_something
        do_something()

    @pyfile
    def test_module():
        # import_and_enable_debugger()
        def do_something():
            print('break here')

    bp_line = 3
    with DebugSession() as session:
        session.initialize(
            target=(run_as, code_to_debug),
            start_method=start_method,
            ignore_unobserved=[Event('stopped'), Event('continued')],
        )
        session.set_breakpoints(test_module, [bp_line])
        session.start_debugging()

        hit = session.wait_for_thread_stopped()
        resp_stacktrace = session.send_request('stackTrace', arguments={
            'threadId': hit.thread_id,
            'format': {'module': module, 'line': line},
        }).wait_for_response()
        assert resp_stacktrace.body['totalFrames'] > 0
        frames = resp_stacktrace.body['stackFrames']

        assert line == (frames[0]['name'].find(': ' + str(bp_line)) > -1)

        assert module == (frames[0]['name'].find('test_module') > -1)

        session.send_request('continue').wait_for_response(freeze=False)
        session.wait_for_exit()


def test_module_events(pyfile, run_as, start_method):
    @pyfile
    def module2():
        # import_and_enable_debugger()
        def do_more_things():
            print('done')

    @pyfile
    def module1():
        # import_and_enable_debugger()
        import module2
        def do_something():
            module2.do_more_things()

    @pyfile
    def test_code():
        from dbgimporter import import_and_enable_debugger
        import_and_enable_debugger()
        from module1 import do_something
        do_something()

    bp_line = 3
    with DebugSession() as session:
        session.initialize(
            target=(run_as, test_code),
            start_method=start_method,
            ignore_unobserved=[Event('stopped'), Event('continued')],
        )
        session.set_breakpoints(module2, [bp_line])
        session.start_debugging()

        session.wait_for_thread_stopped()
        modules = session.all_occurrences_of(Event('module'))
        modules = [(m.body['module']['name'], m.body['module']['path']) for m in modules]
        assert modules[:3] == [
            ('module2', ANY.path(module2)),
            ('module1', ANY.path(module1)),
            ('__main__', ANY.path(test_code)),
        ]

        session.send_request('continue').wait_for_response(freeze=False)
        session.wait_for_exit()
