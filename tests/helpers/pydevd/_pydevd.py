from collections import namedtuple
import sys
try:
    from urllib.parse import quote, unquote
except ImportError:
    from urllib import quote, unquote

from _pydevd_bundle import pydevd_comm

from tests.helpers.protocol import StreamFailure

# TODO: Everything here belongs in a proper pydevd package.


if sys.version_info[0] > 2:
    basestring = str


def parse_message(msg):
    """Return a message object for the given "msg" data."""
    if type(msg) is bytes:
        return Message.from_bytes(msg)
    elif isinstance(msg, str):
        return Message.from_bytes(msg)
    elif type(msg) is RawMessage:
        return msg.msg
    elif type(msg) is Message:
        return msg
    elif isinstance(msg, tuple):
        return Message(*msg)
    else:
        raise NotImplementedError


def encode_message(msg):
    """Return the message, serialized to the line-format."""
    raw = msg.as_bytes()
    if not raw.endswith(b'\n'):
        raw += b'\n'
    return raw


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

    @property
    def msg(self):
        try:
            return self._msg
        except AttributeError:
            self._msg = Message.from_bytes(self.bytes)
            return self._msg

    def as_bytes(self):
        """Return the line-formatted bytes corresponding to the message."""
        return self.bytes


class CMDID(int):
    """A PyDevd command ID."""

    @classmethod
    def from_raw(cls, raw):
        if isinstance(raw, cls):
            return raw
        else:
            return cls(raw)

    def __repr__(self):
        return '<{} {}>'.format(self.name, self)

    @property
    def name(self):
        return pydevd_comm.ID_TO_MEANING.get(str(self), '???')


class Message(namedtuple('Message', 'cmdid seq payload')):
    """A de-seralized PyDevd message."""

    @classmethod
    def from_bytes(cls, raw):
        """Return a RawMessage corresponding to the given raw message."""
        raw = RawMessage.from_bytes(raw)
        parts = raw.bytes.split(b'\t', 2)
        return cls(*parts)

    @classmethod
    def parse_payload(cls, payload):
        """Return the de-serialized payload."""
        if isinstance(payload, bytes):
            payload = payload.decode('utf-8')
        if isinstance(payload, basestring):
            text = unquote(payload)
            return cls._parse_payload_text(text)
        elif hasattr(payload, 'as_text'):
            return payload
        else:
            raise ValueError('unsupported payload {!r}'.format(payload))

    @classmethod
    def _parse_payload_text(cls, text):
        # TODO: convert to the appropriate payload type.
        return text

    def __new__(cls, cmdid, seq, payload):
        if cmdid or cmdid == 0:
            cmdid = CMDID.from_raw(cmdid)
        else:
            cmdid = None
        seq = int(seq) if seq or seq == 0 else None
        payload = cls.parse_payload(payload)
        self = super(Message, cls).__new__(cls, cmdid, seq, payload)
        return self

    def __init__(self, *args, **kwargs):
        if self.cmdid is None:
            raise TypeError('missing cmdid')
        if self.seq is None:
            raise TypeError('missing seq')

    def as_bytes(self):
        """Return the line-formatted bytes corresponding to the message."""
        try:
            payload_as_text = self.payload.as_text
        except AttributeError:
            text = self.payload
        else:
            text = payload_as_text()
        payload = quote(text)
        data = '{}\t{}\t{}'.format(self.cmdid, self.seq, payload)
        return data.encode('utf-8')
