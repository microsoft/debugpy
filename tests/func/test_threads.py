# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

import platform
import pytest

from tests.helpers import get_marked_line_numbers
from tests.helpers.session import DebugSession


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
        print('check here')  # @bp
        stop = True

    line_numbers = get_marked_line_numbers(code_to_debug)
    with DebugSession() as session:
        session.initialize(
            target=(run_as, code_to_debug),
            start_method=start_method,
            program_args=[str(count)],
        )
        session.set_breakpoints(code_to_debug, [line_numbers['bp']])
        session.start_debugging()
        session.wait_for_thread_stopped()
        resp_threads = session.send_request('threads').wait_for_response()

        assert len(resp_threads.body['threads']) == count

        session.send_request('continue').wait_for_response(freeze=False)
        session.wait_for_exit()


@pytest.mark.skipif(
    platform.system() not in ['Windows', 'Linux', 'Darwin'],
    reason='Test not implemented on ' + platform.system())
def test_debug_this_thread(pyfile, run_as, start_method):

    @pyfile
    def code_to_debug():
        from dbgimporter import import_and_enable_debugger
        import_and_enable_debugger()

        import platform
        import ptvsd
        import threading

        def foo(x):
            ptvsd.debug_this_thread()
            event.set()  # @bp
            return 0

        event = threading.Event()

        if platform.system() == 'Windows':
            from ctypes import CFUNCTYPE, c_void_p, c_size_t, c_uint32, windll
            thread_func_p = CFUNCTYPE(c_uint32, c_void_p)
            thread_func = thread_func_p(foo)  # must hold a reference to wrapper during the call
            assert windll.kernel32.CreateThread(c_void_p(0), c_size_t(0), thread_func, c_void_p(0), c_uint32(0), c_void_p(0))
        elif platform.system() == 'Linux' or platform.system() == 'Darwin':
            from ctypes import CDLL, CFUNCTYPE, byref, c_void_p, c_ulong
            from ctypes.util import find_library
            libpthread = CDLL(find_library('libpthread'))
            thread_func_p = CFUNCTYPE(c_void_p, c_void_p)
            thread_func = thread_func_p(foo)  # must hold a reference to wrapper during the call
            assert not libpthread.pthread_create(byref(c_ulong(0)), c_void_p(0), thread_func, c_void_p(0))
        else:
            assert False

        event.wait()

    line_numbers = get_marked_line_numbers(code_to_debug)

    with DebugSession() as session:
        session.initialize(
            target=(run_as, code_to_debug),
            start_method=start_method,
        )
        session.set_breakpoints(code_to_debug, [line_numbers['bp']])
        session.start_debugging()

        session.wait_for_thread_stopped()
        session.send_request('continue').wait_for_response(freeze=False)
        session.wait_for_exit()
