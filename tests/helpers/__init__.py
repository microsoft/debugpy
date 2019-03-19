# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

import os
import re
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


def get_unique_port(base):
    # Different worker processes need to use different ports,
    # for those scenarios where one is specified explicitly.
    try:
        worker_id = os.environ['PYTEST_XDIST_WORKER']
        n = int(worker_id[2:])  # e.g. 'gw123'
    except KeyError:
        n = 0
    return base + n


# Given a path to a Python source file, extracts line numbers for
# all lines that are marked with #@. For example, given this file:
#
#   print(1) #@foo
#   print(2)
#   print(3) #@bar
#
# the function will return:
#
#   {'foo': 1, 'bar': 3}
#
def get_marked_line_numbers(path):
    with open(path) as f:
        lines = {}
        for i, line in enumerate(f):
            match = re.search(r'#\s*@\s*(.*?)\s*$', line)
            if match:
                marker = match.group(1)
                lines[marker] = i + 1
    return lines


from .printer import print
