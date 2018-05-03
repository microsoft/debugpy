from collections import namedtuple
import json
import sys

from debugger_protocol.messages import wireformat
from tests.helpers.protocol import StreamFailure

# TODO: Use more of the code from debugger_protocol.


if sys.version_info[0] > 2:
    unicode = str


class ProtocolMessageError(Exception): pass  # noqa
class MalformedMessageError(ProtocolMessageError): pass  # noqa
class IncompleteMessageError(MalformedMessageError): pass  # noqa
class UnsupportedMessageTypeError(ProtocolMessageError): pass  # noqa


def parse_message(msg):
    """Return a message object for the given "msg" data."""
    if type(msg) is str or type(msg) is unicode:
        data = json.loads(msg)
    elif isinstance(msg, bytes):
        data = json.loads(msg.decode('utf-8'))
    elif type(msg) is RawMessage:
        try:
            msg.data['seq']
            msg.data['type']
        except KeyError:
            return msg
        return parse_message(msg.data)
    elif isinstance(msg, ProtocolMessage):
        if msg.TYPE is not None:
            return msg
        try:
            ProtocolMessage._look_up(msg.type)
        except UnsupportedMessageTypeError:
            return msg
        data = msg.as_data()
    else:
        data = msg

    cls = look_up(data)
    try:
        return cls.from_data(**data)
    except IncompleteMessageError:
        # TODO: simply fail?
        return RawMessage.from_data(**data)


def encode_message(msg):
    """Return the line-formatted bytes for the message."""
    return wireformat.as_bytes(msg)


def iter_messages(stream, stop=lambda: False):
    """Yield the correct message for each line-formatted one found."""
    while not stop():
        try:
            #msg = wireformat.read(stream, lambda _: RawMessage)
            msg = wireformat.read(stream, look_up)
            if msg is None:  # EOF
                break
            yield msg
        except Exception as exc:
            yield StreamFailure('recv', None, exc)


def look_up(data):
    """Return the message type to use."""
    try:
        msgtype = data['type']
    except KeyError:
        # TODO: return RawMessage?
        ProtocolMessage._check_data(data)
    try:
        return ProtocolMessage._look_up(msgtype)
    except UnsupportedMessageTypeError:
        # TODO: return Message?
        raise


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


class ProtocolMessage(object):
    """The base type for VSC debug adapter protocol message."""

    TYPE = None

    @classmethod
    def from_data(cls, **data):
        """Return a message for the given JSON-decoded data."""
        try:
            return cls(**data)
        except TypeError:
            cls._check_data(data)
            raise

    @classmethod
    def _check_data(cls, data):
        missing = set(cls._fields) - set(data)
        if missing:
            raise IncompleteMessageError(','.join(missing))

    @classmethod
    def _look_up(cls, msgtype):
        if msgtype == 'request':
            return Request
        elif msgtype == 'response':
            return Response
        elif msgtype == 'event':
            return Event
        else:
            raise UnsupportedMessageTypeError(msgtype)

    def __new__(cls, seq, type, **kwargs):
        if cls is ProtocolMessage:
            return Message(seq, type, **kwargs)
        seq = int(seq)
        type = str(type) if type else None
        unused = {k: kwargs.pop(k)
                  for k in tuple(kwargs)
                  if k not in cls._fields}
        self = super(ProtocolMessage, cls).__new__(cls, seq, type, **kwargs)
        self._unused = unused
        return self

    def __init__(self, *args, **kwargs):
        if self.TYPE is None:
            if self.type is None:
                raise TypeError('missing type')
        elif self.type != self.TYPE:
            msg = 'wrong type (expected {!r}, go {!r}'
            raise ValueError(msg.format(self.TYPE, self.type))

    def __repr__(self):
        raw = super(ProtocolMessage, self).__repr__()
        if self.TYPE is None:
            return raw
        return ', '.join(part
                         for part in raw.split(', ')
                         if not part.startswith('type='))

    @property
    def unused(self):
        return dict(self._unused)

    def as_data(self):
        """Return the corresponding data, ready to be JSON-encoded."""
        data = self._asdict()
        data.update(self._unused)
        return data


class Message(ProtocolMessage, namedtuple('Message', 'seq type')):
    """A generic DAP message."""

    def __getattr__(self, name):
        try:
            return self._unused[name]
        except KeyError:
            raise AttributeError(name)


class Request(ProtocolMessage,
              namedtuple('Request', 'seq type command arguments')):
    """A DAP request message."""

    TYPE = 'request'

    def __new__(cls, seq, type, command, arguments, **unused):
        # TODO: Make "arguments" immutable?
        return super(Request, cls).__new__(
            cls,
            seq,
            type,
            command=command,
            arguments=arguments,
            **unused
        )


class Response(ProtocolMessage,
               namedtuple('Response',
                          'seq type request_seq command success message body'),
               ):
    """A DAP response message."""

    TYPE = 'response'

    def __new__(cls, seq, type, request_seq, command, success, message, body,
                **unused):
        # TODO: Make "body" immutable?
        return super(Response, cls).__new__(
            cls,
            seq,
            type,
            request_seq=request_seq,
            command=command,
            success=success,
            message=message,
            body=body,
            **unused
        )


class Event(ProtocolMessage, namedtuple('Event', 'seq type event body')):
    """A DAP event message."""

    TYPE = 'event'

    def __new__(cls, seq, type, event, body, **unused):
        # TODO: Make "body" immutable?
        return super(Event, cls).__new__(
            cls,
            seq,
            type,
            event=event,
            body=body,
            **unused
        )
