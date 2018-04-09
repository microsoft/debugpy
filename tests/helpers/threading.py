from __future__ import absolute_import

import threading
import warnings


def get_locked_and_waiter():
    lock = threading.Lock()
    lock.acquire()

    def wait(timeout=1.0, reason=None):
        if lock.acquire(timeout=timeout):
            lock.release()
        else:
            msg = 'timed out waiting'
            if reason:
                msg += ' for {}'.format(reason)
            warnings.warn(msg)
    return lock, wait
