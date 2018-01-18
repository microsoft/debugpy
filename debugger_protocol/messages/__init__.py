

MESSAGE_TYPES = {}
MESSAGE_TYPE_KEYS = {}


def register(cls, msgtype=None, typekey=None, key=None):
    """Add the message class to the registry.

    The class is also fixed up if necessary.
    """
    if not isinstance(cls, type):
        raise RuntimeError('may not be used as a decorator factory.')

    if msgtype is None:
        if cls.TYPE is None:
            raise RuntimeError('class missing TYPE')
        msgtype = cls.TYPE
    if typekey is None:
        if cls.TYPE_KEY is None:
            raise RuntimeError('class missing TYPE_KEY')
        typekey = cls.TYPE_KEY
    if key is None:
        key = getattr(cls, typekey,
                      getattr(cls, typekey.upper(), None))
        if not key:
            raise RuntimeError('missing type key attribute')

    try:
        registered = MESSAGE_TYPES[msgtype]
    except KeyError:
        registered = MESSAGE_TYPES[msgtype] = {}
        MESSAGE_TYPE_KEYS[msgtype] = typekey
    else:
        if typekey != MESSAGE_TYPE_KEYS[msgtype]:
            msg = 'mismatch on TYPE_KEY ({!r} != {!r})'
            raise RuntimeError(
                    msg.format(typekey, MESSAGE_TYPE_KEYS[msgtype]))

    if key in registered:
        raise RuntimeError('{}:{} already registered'.format(msgtype, key))
    registered[key] = cls

    # XXX init args

    return cls


class Message(object):
    """The API for register-able message types."""

    TYPE = None
    TYPE_KEY = None

    @classmethod
    def from_data(cls, **kwargs):
        """Return an instance based on the given raw data."""
        raise NotImplementedError

    def as_data(self):
        """Return serializable data for the instance."""
        raise NotImplementedError


# Force registration.
from .requests import *  # noqa
from .events import *  # noqa
