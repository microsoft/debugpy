# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

from tests.helpers.pattern import Path
from tests.helpers.session import DebugSession
import pytest


@pytest.mark.parametrize('start_method', ['launch'])
def test_stop_on_entry(run_as, start_method, tmpdir):
    testfile = tmpdir.join('test.py')
    with testfile.open('w') as stream:
        stream.write('''
stop_here = 1
print('done')
''')

    with DebugSession() as session:
        session.initialize(
            target=(run_as, str(testfile)),
            start_method=start_method,
            debug_options=['StopOnEntry'],
        )

        session.start_debugging()
        hit = session.wait_for_thread_stopped()
        frames = hit.stacktrace.body['stackFrames']
        assert frames[0]['source']['path'] == Path(str(testfile))

        session.send_request('continue').wait_for_response(freeze=False)
        session.wait_for_exit()
