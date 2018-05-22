
def noop(*args, **kwargs):
    """Do nothing."""


class Closeable(object):

    def __init__(self):
        self._closed = False

    def __del__(self):
        if not self._closed:
            self.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    @property
    def closed(self):
        return self._closed

    def close(self):
        if self._closed:
            return
        self._closed = True

        self._close()

    # implemented by subclasses

    def _close(self):
        raise NotImplementedError
