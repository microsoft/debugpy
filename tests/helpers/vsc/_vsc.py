from collections import namedtuple
import json

from debugger_protocol.messages import wireformat
from tests.helpers.protocol import StreamFailure

# TODO: Use more of the code from debugger_protocol.


def parse_message(msg):
    """Return a message object for the given "msg" data."""
    if type(msg) is str:
        data = json.loads(msg)
    elif isinstance(msg, bytes):
        data = json.loads(msg.decode('utf-8'))
    elif type(msg) is RawMessage:
        return msg
    else:
        data = msg
    return RawMessage.from_data(**data)


def encode_message(msg):
    """Return the line-formatted bytes for the message."""
    return wireformat.as_bytes(msg)


def iter_messages(stream, stop=lambda: False):
    """Yield the correct message for each line-formatted one found."""
    while not stop():
        try:
            msg = wireformat.read(stream, lambda _: RawMessage)
            if msg is None:  # EOF
                break
            yield msg
        except Exception as exc:
            yield StreamFailure('recv', None, exc)


class RawMessage(namedtuple('RawMessage', 'data')):
    """A wrapper around a line-formatted debugger protocol message."""

    @classmethod
    def from_data(cls, **data):
        """Return a RawMessage for the given JSON-decoded data."""
        return cls(data)

    def __new__(cls, data):
        if type(data) is cls:
            return data
        self = super(RawMessage, cls).__new__(cls, data)
        return self

    def as_data(self):
        """Return the corresponding data, ready to be JSON-encoded."""
        return self.data
