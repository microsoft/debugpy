

class Readonly(object):
    """For read-only instances."""

    def __setattr__(self, name, value):
        raise AttributeError(
                '{} objects are read-only'.format(type(self).__name__))

    def __delattr__(self, name):
        raise AttributeError(
                '{} objects are read-only'.format(type(self).__name__))

    def _bind_attrs(self, **attrs):
        for name, value in attrs.items():
            object.__setattr__(self, name, value)


class WithRepr(object):

    def _init_args(self):
        # XXX Extract from __init__()...
        return ()

    def __repr__(self):
        args = ', '.join('{}={!r}'.format(arg, value)
                         for arg, value in self._init_args())
        return '{}({})'.format(type(self).__name__, args)
