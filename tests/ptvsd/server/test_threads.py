# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import platform
import pytest
import time

from tests import debug


@pytest.mark.parametrize("count", [1, 3])
def test_thread_count(pyfile, start_method, run_as, count):
    @pyfile
    def code_to_debug():
        import threading
        import time
        import sys
        import debug_me  # noqa

        stop = False

        def worker(tid, offset):
            i = 0
            global stop
            while not stop:
                time.sleep(0.01)
                i += 1

        threads = []
        if sys.argv[1] != "1":
            for i in [111, 222]:
                thread = threading.Thread(target=worker, args=(i, len(threads)))
                threads.append(thread)
                thread.start()
        print("check here")  # @bp
        stop = True

    with debug.Session(start_method) as session:
        session.configure(
            run_as, code_to_debug,
            args=[str(count)],
        )
        session.set_breakpoints(code_to_debug, [code_to_debug.lines["bp"]])
        session.start_debugging()
        session.wait_for_stop()
        resp_threads = session.send_request("threads").wait_for_response()

        assert len(resp_threads.body["threads"]) == count

        session.request_continue()


@pytest.mark.parametrize('stepping_resumes_all_threads', [None, True, False])
def test_step_multi_threads(pyfile, run_as, start_method, stepping_resumes_all_threads):

    @pyfile
    def code_to_debug():
        '''
        After breaking on the thread 1, thread 2 should pause waiting for the event1 to be set,
        so, when we step return on thread 1, the program should finish if all threads are resumed
        or should keep waiting for the thread 2 to run if only thread 1 is resumed.
        '''
        import threading
        import debug_me  # noqa

        event0 = threading.Event()
        event1 = threading.Event()
        event2 = threading.Event()
        event3 = threading.Event()

        def _thread1():
            while not event0.is_set():
                event0.wait(timeout=.001)

            event1.set()  # @break_thread_1

            while not event2.is_set():
                event2.wait(timeout=.001)
            # Note: we can only get here if thread 2 is also released.

            event3.set()

        def _thread2():
            event0.set()

            while not event1.is_set():
                event1.wait(timeout=.001)

            event2.set()

            while not event3.is_set():
                event3.wait(timeout=.001)

        threads = [
            threading.Thread(target=_thread1, name='thread1'),
            threading.Thread(target=_thread2, name='thread2'),
        ]
        for t in threads:
            t.start()

        for t in threads:
            t.join()

    with debug.Session(start_method) as session:
        session.configure(run_as, code_to_debug, steppingResumesAllThreads=stepping_resumes_all_threads)
        session.set_breakpoints(code_to_debug, [code_to_debug.lines['break_thread_1']])
        session.start_debugging()
        stop_info = session.wait_for_stop()
        resp_threads = session.send_request('threads').wait_for_response()
        assert len(resp_threads.body['threads']) == 3
        thread_name_to_id = dict((t['name'], t['id']) for t in resp_threads.body['threads'])
        assert stop_info.thread_id == thread_name_to_id['thread1']

        if stepping_resumes_all_threads or stepping_resumes_all_threads is None:
            # stepping_resumes_all_threads == None means we should use default (which is to
            # resume all threads) -- in which case stepping out will exit the program.
            session.send_request('stepOut', {'threadId': stop_info.thread_id}).wait_for_response(freeze=False)

        else:
            session.send_request('stepOut', {'threadId': stop_info.thread_id}).wait_for_response()
            # Wait a second and check that threads are still there.
            time.sleep(1)

            resp_stacktrace = session.send_request('stackTrace', arguments={
                'threadId': thread_name_to_id['thread1'],
            }).wait_for_response()
            assert '_thread1' in [x['name'] for x in resp_stacktrace.body['stackFrames']]

            resp_stacktrace = session.send_request('stackTrace', arguments={
                'threadId': thread_name_to_id['thread2'],
            }).wait_for_response()
            assert '_thread2' in [x['name'] for x in resp_stacktrace.body['stackFrames']]

            session.request_continue()


@pytest.mark.skipif(
    platform.system() not in ["Windows", "Linux", "Darwin"],
    reason="Test not implemented on " + platform.system(),
)
def test_debug_this_thread(pyfile, start_method, run_as):
    @pyfile
    def code_to_debug():
        from debug_me import ptvsd
        import platform
        import threading

        def foo(x):
            ptvsd.debug_this_thread()
            event.set()  # @bp
            return 0

        event = threading.Event()

        if platform.system() == "Windows":
            from ctypes import CFUNCTYPE, c_void_p, c_size_t, c_uint32, windll

            thread_func_p = CFUNCTYPE(c_uint32, c_void_p)
            thread_func = thread_func_p(
                foo
            )  # must hold a reference to wrapper during the call
            assert windll.kernel32.CreateThread(
                c_void_p(0),
                c_size_t(0),
                thread_func,
                c_void_p(0),
                c_uint32(0),
                c_void_p(0),
            )
        elif platform.system() == "Linux" or platform.system() == "Darwin":
            from ctypes import CDLL, CFUNCTYPE, byref, c_void_p, c_ulong
            from ctypes.util import find_library

            libpthread = CDLL(find_library("libpthread"))
            thread_func_p = CFUNCTYPE(c_void_p, c_void_p)
            thread_func = thread_func_p(
                foo
            )  # must hold a reference to wrapper during the call
            assert not libpthread.pthread_create(
                byref(c_ulong(0)), c_void_p(0), thread_func, c_void_p(0)
            )
        else:
            assert False

        event.wait()

    with debug.Session(start_method) as session:
        session.configure(run_as, code_to_debug)
        session.set_breakpoints(code_to_debug, [code_to_debug.lines["bp"]])
        session.start_debugging()

        session.wait_for_stop()
        session.request_continue()
