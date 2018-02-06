from debugger_protocol._base import Readonly, WithRepr
from debugger_protocol.arg import param_from_datatype
from . import MESSAGE_TYPES, Message

"""
From the schema:

MESSAGE = [
    name
    base
    description
    props: [PROPERTY + (properties: [PROPERTY])]
]

PROPERTY = [
    name
    type: choices (one or a list)
    (enum/_enum)
    description
    required: True/False (default: False)
]

inheritance: override properties of base
"""


class ProtocolMessage(Readonly, WithRepr, Message):
    """Base class of requests, responses, and events."""

    _reqid = 0
    TYPE = None

    @classmethod
    def from_data(cls, type, seq, **kwargs):
        """Return an instance based on the given raw data."""
        return cls(type=type, seq=seq, **kwargs)

    @classmethod
    def _next_reqid(cls):
        reqid = ProtocolMessage._reqid
        ProtocolMessage._reqid += 1
        return reqid

    _NOT_SET = object()

    def __init__(self, seq=_NOT_SET, **kwargs):
        type = kwargs.pop('type', self.TYPE)
        if seq is self._NOT_SET:
            seq = self._next_reqid()
        self._bind_attrs(
            type=type or None,
            seq=int(seq) if seq or seq == 0 else None,
        )
        self._validate()

    def _validate(self):
        if self.type is None:
            raise TypeError('missing type')
        elif self.TYPE is not None and self.type != self.TYPE:
            raise ValueError('type must be {!r}'.format(self.TYPE))
        elif self.type not in MESSAGE_TYPES:
            raise ValueError('unsupported type {!r}'.format(self.type))

        if self.seq is None:
            raise TypeError('missing seq')
        elif self.seq < 0:
            msg = '"seq" must be a non-negative int, got {!r}'
            raise ValueError(msg.format(self.seq))

    def _init_args(self):
        if self.TYPE is None:
            yield ('type', self.type)
        yield ('seq', self.seq)

    def as_data(self):
        """Return serializable data for the instance."""
        data = {
            'type': self.type,
            'seq': self.seq,
        }
        return data


##################################

class Request(ProtocolMessage):
    """A client or server-initiated request."""

    TYPE = 'request'
    TYPE_KEY = 'command'

    COMMAND = None
    ARGUMENTS = None
    ARGUMENTS_REQUIRED = None

    @classmethod
    def from_data(cls, type, seq, command, arguments=None):
        """Return an instance based on the given raw data."""
        return super(Request, cls).from_data(
            type, seq,
            command=command,
            arguments=arguments,
        )

    @classmethod
    def _arguments_required(cls):
        if cls.ARGUMENTS_REQUIRED is None:
            return cls.ARGUMENTS is not None
        return cls.ARGUMENTS_REQUIRED

    def __init__(self, arguments=None, **kwargs):
        command = kwargs.pop('command', self.COMMAND)
        args = None
        if arguments is not None:
            try:
                arguments = dict(arguments)
            except TypeError:
                pass
            if self.ARGUMENTS is not None:
                param = param_from_datatype(self.ARGUMENTS)
                args = param.bind(arguments)
                if args is None:
                    raise TypeError('bad arguments {!r}'.format(arguments))
                arguments = args.coerce()
        self._bind_attrs(
            command=command or None,
            arguments=arguments or None,
            _args=args,
        )
        super(Request, self).__init__(**kwargs)

    def _validate(self):
        super(Request, self)._validate()

        if self.command is None:
            raise TypeError('missing command')
        elif self.COMMAND is not None and self.command != self.COMMAND:
            raise ValueError('command must be {!r}'.format(self.COMMAND))

        if self.arguments is None:
            if self._arguments_required():
                raise TypeError('missing arguments')
        else:
            if self.ARGUMENTS is None:
                raise TypeError('got unexpected arguments')
            self._args.validate()

    def _init_args(self):
        if self.COMMAND is None:
            yield ('command', self.command)
        if self.arguments is not None:
            yield ('arguments', self.arguments)
        yield ('seq', self.seq)

    def as_data(self):
        """Return serializable data for the instance."""
        data = super(Request, self).as_data()
        data.update({
            'command': self.command,
        })
        if self.arguments is not None:
            data.update({
                'arguments': self.arguments.as_data(),
            })
        return data


class Response(ProtocolMessage):
    """Response to a request."""

    TYPE = 'response'
    TYPE_KEY = 'command'

    COMMAND = None
    BODY = None
    ERROR_BODY = None
    BODY_REQUIRED = None
    ERROR_BODY_REQUIRED = None

    @classmethod
    def from_data(cls, type, seq, request_seq, command, success,
                  body=None, message=None):
        """Return an instance based on the given raw data."""
        return super(Response, cls).from_data(
            type, seq,
            request_seq=request_seq,
            command=command,
            success=success,
            body=body,
            message=message,
        )

    @classmethod
    def _body_required(cls, success=True):
        required = cls.BODY_REQUIRED if success else cls.ERROR_BODY_REQUIRED
        if required is not None:
            return required
        bodyclass = cls.BODY if success else cls.ERROR_BODY
        return bodyclass is not None

    def __init__(self, request_seq, body=None, message=None, success=True,
                 **kwargs):
        command = kwargs.pop('command', self.COMMAND)
        reqseq = request_seq
        bodyarg = None
        if body is not None:
            try:
                body = dict(body)
            except TypeError:
                pass
            bodyclass = self.BODY if success else self.ERROR_BODY
            if bodyclass is not None:
                param = param_from_datatype(bodyclass)
                bodyarg = param.bind(body)
                if bodyarg is None:
                    raise TypeError('bad body type {!r}'.format(body))
                body = bodyarg.coerce()
        self._bind_attrs(
            command=command or None,
            request_seq=int(reqseq) if reqseq or reqseq == 0 else None,
            body=body or None,
            _bodyarg=bodyarg,
            message=message or None,
            success=bool(success),
        )
        super(Response, self).__init__(**kwargs)

    def _validate(self):
        super(Response, self)._validate()

        if self.request_seq is None:
            raise TypeError('missing request_seq')
        elif self.request_seq < 0:
            msg = 'request_seq must be a non-negative int, got {!r}'
            raise ValueError(msg.format(self.request_seq))

        if not self.command:
            raise TypeError('missing command')
        elif self.COMMAND is not None and self.command != self.COMMAND:
            raise ValueError('command must be {!r}'.format(self.COMMAND))

        if self.body is None:
            if self._body_required(self.success):
                raise TypeError('missing body')
        elif self._bodyarg is None:
            raise ValueError('got unexpected body')
        else:
            self._bodyarg.validate()

        if not self.success and not self.message:
            raise TypeError('missing message')

    def _init_args(self):
        if self.COMMAND is None:
            yield ('command', self.command)
        yield ('request_seq', self.request_seq)
        yield ('success', self.success)
        if not self.success:
            yield ('message', self.message)
        if self.body is not None:
            yield ('body', self.body)
        yield ('seq', self.seq)

    def as_data(self):
        """Return serializable data for the instance."""
        data = super(Response, self).as_data()
        data.update({
            'request_seq': self.request_seq,
            'command': self.command,
            'success': self.success,
        })
        if self.body is not None:
            data.update({
                'body': self.body.as_data(),
            })
        if self.message is not None:
            data.update({
                'message': self.message,
            })
        return data


##################################

class Event(ProtocolMessage):
    """Server-initiated event."""

    TYPE = 'event'
    TYPE_KEY = 'event'

    EVENT = None
    BODY = None
    BODY_REQUIRED = None

    @classmethod
    def from_data(cls, type, seq, event, body=None):
        """Return an instance based on the given raw data."""
        return super(Event, cls).from_data(type, seq, event=event, body=body)

    @classmethod
    def _body_required(cls):
        if cls.BODY_REQUIRED is None:
            return cls.BODY is not None
        return cls.BODY_REQUIRED

    def __init__(self, body=None, **kwargs):
        event = kwargs.pop('event', self.EVENT)
        bodyarg = None
        if body is not None:
            try:
                body = dict(body)
            except TypeError:
                pass
            if self.BODY is not None:
                param = param_from_datatype(self.BODY)
                bodyarg = param.bind(body)
                if bodyarg is None:
                    raise TypeError('bad body type {!r}'.format(body))
                body = bodyarg.coerce()

        self._bind_attrs(
            event=event or None,
            body=body or None,
            _bodyarg=bodyarg,
        )
        super(Event, self).__init__(**kwargs)

    def _validate(self):
        super(Event, self)._validate()

        if self.event is None:
            raise TypeError('missing event')
        if self.EVENT is not None and self.event != self.EVENT:
            msg = 'event must be {!r}, got {!r}'
            raise ValueError(msg.format(self.EVENT, self.event))

        if self.body is None:
            if self._body_required():
                raise TypeError('missing body')
        elif self._bodyarg is None:
            raise ValueError('got unexpected body')
        else:
            self._bodyarg.validate()

    def _init_args(self):
        if self.EVENT is None:
            yield ('event', self.event)
        if self.body is not None:
            yield ('body', self.body)
        yield ('seq', self.seq)

    @property
    def name(self):
        return self.event

    def as_data(self):
        """Return serializable data for the instance."""
        data = super(Event, self).as_data()
        data.update({
            'event': self.event,
        })
        if self.body is not None:
            data.update({
                'body': self.body.as_data(),
            })
        return data
