import inspect
import os
import os.path
import time


class LockTimeoutError(RuntimeError):
    pass


##################################
# lock files

# TODO: Support a nonce for lockfiles?

def _acquire_lockfile(filename, timeout):
    # Wait until it does not exist.
    for _ in range(int(timeout * 10) + 1):
        if not os.path.exists(filename):
            break
        time.sleep(0.1)
    else:
        if os.path.exists(filename):
            raise LockTimeoutError(
                'timed out waiting for lockfile %r' % filename)
    # Create the file.
    with open(filename, 'w'):
        pass


def _release_lockfile(filename):
    try:
        os.remove(filename)
    except OSError:
        if not os.path.exists(filename):
            raise RuntimeError('lockfile not held')
        # TODO: Fail here?
        pass


_ACQUIRE_LOCKFILE = """
# <- START ACQUIRE LOCKFILE SCRIPT ->
import os.path
import time
class LockTimeoutError(RuntimeError):
    pass
%s
_acquire_lockfile({!r}, {!r})
# <- END ACQUIRE LOCKFILE SCRIPT ->
""" % inspect.getsource(_acquire_lockfile).strip()

_RELEASE_LOCKFILE = """
# <- START RELEASE LOCKFILE SCRIPT ->
import os
import os.path
%s
_release_lockfile({!r})
# <- END RELEASE LOCKFILE SCRIPT ->
""" % inspect.getsource(_release_lockfile).strip()


class Lockfile(object):
    """A wrapper around a lock file."""

    def __init__(self, filename):
        self._filename = filename

    def __repr__(self):
        return '{}(filename={!r})'.format(
            type(self).__name__,
            self._filename,
        )

    def __str__(self):
        return self._filename

    @property
    def filename(self):
        return self._filename

    def acquire(self, timeout=5.0):
        _acquire_lockfile(self._filename, timeout)

    def acquire_script(self, timeout=5.0):
        return _ACQUIRE_LOCKFILE.format(self._filename, timeout)

    def release(self):
        _release_lockfile(self._filename)

    def release_script(self):
        return _RELEASE_LOCKFILE.format(self._filename)

    def wait_for_script(self):
        """Return (done script, wait func) after acquiring."""
        def wait(**kwargs):
            self.acquire(**kwargs)
            self.release()
        self.acquire()
        return self.release_script(), wait

    def wait_in_script(self, **kwargs):
        """Return (done func, wait script) after acquiring."""
        script = self.acquire_script(**kwargs) + self.release_script()
        self.acquire()
        return self.release, script
