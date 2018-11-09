# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

__all__ = ['print', 'wait_for_output']

import threading
from ptvsd.compat import queue
from pytests.helpers import timestamp, colors


real_print = print
print_queue = queue.Queue()


def print(*args, **kwargs):
    """Like builtin print(), but synchronized across multiple threads,
    and adds a timestamp.
    """
    timestamped = kwargs.pop('timestamped', True)
    t = timestamp() if timestamped else None
    print_queue.put((t, args, kwargs))


def wait_for_output():
    print_queue.join()


def print_worker():
    while True:
        t, args, kwargs = print_queue.get()
        if t is not None:
            t = colors.LIGHT_BLACK + ('@%09.6f:' % t) + colors.RESET
            args = (t,) + args
        real_print(*args, **kwargs)
        print_queue.task_done()


print_thread = threading.Thread(target=print_worker, name='printer')
print_thread.daemon = True
print_thread.start()
