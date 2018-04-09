from __future__ import absolute_import

import threading
import warnings


def get_locked_and_waiter(timeout=1.0):
    _timeout = timeout
    lock = threading.Lock()
    lock.acquire()

    def wait(timeout=_timeout, reason=None):
        if timeout is None:
            timeout = _timeout
        if lock.acquire(timeout=timeout):
            lock.release()
        else:
            msg = 'timed out waiting'
            if reason:
                msg += ' for {}'.format(reason)
            warnings.warn(msg)
    return lock, wait
