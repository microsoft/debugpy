from __future__ import absolute_import

import sys
import threading
import time
import warnings


if sys.version_info < (3,):
    def acquire_with_timeout(lock, timeout):
        if lock.acquire(False):
            return True
        for _ in range(int(timeout * 10)):
            time.sleep(0.1)
            if lock.acquire(False):
                return True
        else:
            return False
else:
    def acquire_with_timeout(lock, timeout):
        return lock.acquire(timeout=timeout)


def get_locked_and_waiter(timeout=1.0):
    _timeout = timeout
    lock = threading.Lock()
    lock.acquire()

    def wait(timeout=_timeout, reason=None):
        if timeout is None:
            timeout = _timeout
        if acquire_with_timeout(lock, timeout):
            lock.release()
        else:
            msg = 'timed out waiting'
            if reason:
                msg += ' for {}'.format(reason)
            warnings.warn(msg)
    return lock, wait
