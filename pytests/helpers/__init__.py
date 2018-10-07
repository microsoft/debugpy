# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

import os
import sys
import threading
import time
import traceback


if sys.version_info >= (3, 5):
    clock = time.monotonic
else:
    clock = time.clock


timestamp_zero = clock()

def timestamp():
    return clock() - timestamp_zero


print_lock = threading.Lock()
real_print = print

def print(*args, **kwargs):
    """Like builtin print(), but synchronized using a global lock,
    and adds a timestamp
    """
    from . import colors
    timestamped = kwargs.pop('timestamped', True)
    with print_lock:
        if timestamped:
            t = timestamp()
            real_print(colors.LIGHT_BLACK, end='')
            real_print('@%09.6f: ' % t, end='')
            real_print(colors.RESET, end='')
        real_print(*args, **kwargs)


def dump_stacks():
    """Dump the stacks of all threads except the current thread"""
    current_ident = threading.current_thread().ident
    for thread_ident, frame in sys._current_frames().items():
        if thread_ident == current_ident:
            continue
        for t in threading.enumerate():
            if t.ident == thread_ident:
                thread_name = t.name
                thread_daemon = t.daemon
                break
        else:
            thread_name = '<unknown>'
        print('Stack of %s (%s) in pid %s; daemon=%s' % (thread_name, thread_ident, os.getpid(), thread_daemon))
        print(''.join(traceback.format_stack(frame)))


def dump_stacks_in(secs):
    """Invokes dump_stacks() on a background thread after waiting.

    Can be called from debugged code before the point after which it hangs,
    to determine the cause of the hang while debugging a test.
    """

    def dumper():
        time.sleep(secs)
        dump_stacks()

    thread = threading.Thread(target=dumper)
    thread.daemon = True
    thread.start()
