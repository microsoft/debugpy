from collections import namedtuple

# TODO: Everything here belongs in a proper pydevd package.


class StreamFailure(Exception):
    """Something went wrong while handling messages to/from a stream."""

    def __init__(self, direction, msg, exception):
        err = 'error while processing stream: {!r}'.format(exception)
        super(StreamFailure, self).__init__(self, err)
        self.direction = direction
        self.msg = msg
        self.exception = exception

    def __repr__(self):
        return '{}(direction={!r}, msg={!r}, exception={!r})'.format(
            type(self).__name__,
            self.direction,
            self.msg,
            self.exception,
        )


def iter_messages(stream, stop=lambda: False):
    """Yield the correct message for each line-formatted one found."""
    lines = iter(stream)
    while not stop():
        # TODO: Loop with a timeout instead of waiting indefinitely on recv().
        try:
            line = next(lines)
            if not line.strip():
                continue
            yield parse_message(line)
        except Exception as exc:
            yield StreamFailure('recv', None, exc)


def parse_message(msg):
    """Return a message object for the given "msg" data."""
    if type(msg) is bytes:
        return RawMessage.from_bytes(msg)
    elif isinstance(msg, str):
        return RawMessage.from_bytes(msg)
    elif type(msg) is RawMessage:
        return msg
    else:
        raise NotImplementedError


class RawMessage(namedtuple('RawMessage', 'bytes')):
    """A pydevd message class that leaves the raw bytes unprocessed."""

    @classmethod
    def from_bytes(cls, raw):
        """Return a RawMessage corresponding to the given raw message."""
        return cls(raw)

    def __new__(cls, raw):
        if type(raw) is cls:
            return raw
        if type(raw) is not bytes:
            raw = raw.encode('utf-8')
        raw = raw.rstrip(b'\n')
        self = super(RawMessage, cls).__new__(cls, raw)
        return self

    def as_bytes(self):
        """Return the line-formatted bytes corresponding to the message."""
        return self.bytes
