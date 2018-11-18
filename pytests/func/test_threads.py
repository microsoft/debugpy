# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import
import pytest
from pytests.helpers.timeline import Event
from pytests.helpers.session import DebugSession


@pytest.mark.parametrize('count', [1, 3])
def test_thread_count(pyfile, run_as, start_method, count):
    @pyfile
    def code_to_debug():
        import threading
        import time
        import sys
        from dbgimporter import import_and_enable_debugger
        import_and_enable_debugger()
        stop = False
        def worker(tid, offset):
            i = 0
            global stop
            while not stop:
                time.sleep(0.01)
                i += 1
        threads = []
        if sys.argv[1] != '1':
            for i in [111, 222]:
                thread = threading.Thread(target=worker, args=(i, len(threads)))
                threads.append(thread)
                thread.start()
        print('check here')
        stop = True

    with DebugSession() as session:
        session.initialize(target=(run_as, code_to_debug), start_method=start_method, program_args=[str(count)])
        session.set_breakpoints(code_to_debug, [19])
        session.start_debugging()
        session.wait_for_thread_stopped()
        resp_threads = session.send_request('threads').wait_for_response()

        assert len(resp_threads.body['threads']) == count

        session.send_request('continue').wait_for_response()
        session.wait_for_next(Event('continued'))

        session.wait_for_exit()
