# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

from tests.helpers.pattern import Path
from tests.helpers.session import DebugSession
import pytest


@pytest.mark.parametrize('start_method', ['launch'])
def test_stop_on_entry(pyfile, run_as, start_method):

    @pyfile
    def code_to_debug():
        import backchannel
        from dbgimporter import import_and_enable_debugger
        import_and_enable_debugger()
        backchannel.write_json('done')

    with DebugSession() as session:
        session.initialize(
            target=(run_as, code_to_debug),
            start_method=start_method,
            debug_options=['StopOnEntry'],
            use_backchannel=True,
        )
        session.start_debugging()

        thread_stopped, resp_stacktrace, tid, _ = session.wait_for_thread_stopped(reason='entry')
        frames = resp_stacktrace.body['stackFrames']
        assert frames[0]['line'] == 1
        assert frames[0]['source']['path'] == Path(code_to_debug)

        session.send_request('continue').wait_for_response(freeze=False)
        session.wait_for_termination()

        assert session.read_json() == 'done'

        session.wait_for_exit()