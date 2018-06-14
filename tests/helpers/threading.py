from __future__ import absolute_import

import sys
import threading
import time
import warnings

from ptvsd._util import TimeoutError


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

    def wait(timeout=_timeout, reason=None, fail=False):
        if timeout is None:
            timeout = _timeout
        if acquire_with_timeout(lock, timeout):
            lock.release()
        else:
            msg = 'timed out (after {} seconds) waiting'.format(timeout)
            if reason:
                msg += ' for {}'.format(reason)
            if fail:
                raise TimeoutError(msg)
            warnings.warn(msg, stacklevel=2)
    return lock, wait
