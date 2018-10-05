# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

from ..helpers.pattern import ANY
from ..helpers.timeline import Event


def test_run(debug_session, pyfile):
    @pyfile
    def code_to_debug():
        from pytests.helpers import backchannel
        print('before')
        assert backchannel.read_json() == 1
        print('after')

    timeline = debug_session.timeline
    debug_session.prepare_to_run(filename=code_to_debug, backchannel=True)
    start = debug_session.start_debugging()

    first_thread = (start >> Event('thread', {'reason': 'started', 'threadId': ANY})).wait()
    with timeline.frozen():
        assert (
            timeline.beginning
            >>
            Event('initialized', {})
            >>
            Event('process', {
                'name': code_to_debug,
                'isLocalProcess': True,
                'startMethod': 'launch' if debug_session.method == 'launch' else 'attach',
                'systemProcessId': debug_session.process.pid,
            })
            >>
            first_thread
        ) in timeline

    t = debug_session.write_json(1)
    (t >> Event('terminated', {})).wait()

    debug_session.wait_for_exit()
