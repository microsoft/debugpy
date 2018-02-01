

class Stub(object):
    """A testing double that tracks calls."""

    def __init__(self):
        self.calls = []
        self._exceptions = []

    def set_exceptions(self, *exceptions):
        self._exceptions = list(exceptions)

    def add_call(self, name, *args, **kwargs):
        self.add_call_exact(name, args, kwargs)

    def add_call_exact(self, name, args, kwargs):
        self.calls.append((name, args, kwargs))

    def maybe_raise(self):
        if not self._exceptions:
            return
        exc = self._exceptions.pop(0)
        if exc is None:
            return
        raise exc
