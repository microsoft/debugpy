# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

from ..helpers.pattern import ANY
from ..helpers.timeline import Event


def test_run(debug_session, pyfile):
    @pyfile
    def code_to_debug():
        print('waiting for input')
        input()
        print('got input!')

    debug_session.prepare_to_run(filename=code_to_debug)
    debug_session.start_debugging()

    t = debug_session.wait_until(Event('process') & Event('thread'))
    assert (
        Event('thread', {'reason': 'started', 'threadId': ANY})
        & (
            Event('initialized', {})
            >>
            Event('process', {
                'name': code_to_debug,
                'isLocalProcess': True,
                'startMethod': 'launch' if debug_session.method == 'launch' else 'attach',
                'systemProcessId': debug_session.process.pid,
            })
        )
    ).has_occurred_by(t)

    with debug_session.causing(Event('terminated', {})):
        debug_session.process.communicate(b'0\n')

    debug_session.wait_for_exit()
