import sys


class Counter(object):
    """An introspectable, dynamic alternative to itertools.count()."""

    def __init__(self, start=0, step=1):
        self._start = int(start)
        self._step = int(step)

    def __repr__(self):
        return '{}(start={}, step={})'.format(
            type(self).__name__,
            self.peek(),
            self._step,
        )

    def __iter__(self):
        return self

    def __next__(self):
        try:
            self._last += self._step
        except AttributeError:
            self._last = self._start
        return self._last

    if sys.version_info[0] == 2:
        next = __next__

    @property
    def start(self):
        return self._start

    @property
    def step(self):
        return self._step

    @property
    def last(self):
        try:
            return self._last
        except AttributeError:
            return None

    def peek(self, iterations=1):
        """Return the value that will be used next."""
        try:
            last = self._last
        except AttributeError:
            last = self._start - self._step
        return last + self._step * iterations

    def reset(self, start=None):
        """Set the next value to the given one.

        If no value is provided then the previous start value is used.
        """
        if start is not None:
            self._start = int(start)
        try:
            del self._last
        except AttributeError:
            pass
