from debugger_protocol._base import Readonly, WithRepr


class _ParameterBase(WithRepr):

    def __init__(self, datatype):
        self._datatype = datatype

    def _init_args(self):
        yield ('datatype', self._datatype)

    def __hash__(self):
        try:
            return hash(self._datatype)
        except TypeError:
            return hash(id(self))

    def __eq__(self, other):
        if type(self) is not type(other):
            return NotImplemented
        return self._datatype == other._datatype

    def __ne__(self, other):
        return not (self == other)

    @property
    def datatype(self):
        return self._datatype


class Parameter(_ParameterBase):
    """Base class for different parameter types."""

    def __init__(self, datatype, handler=None):
        super(Parameter, self).__init__(datatype)
        self._handler = handler

    def _init_args(self):
        for item in super(Parameter, self)._init_args():
            yield item
        if self._handler is not None:
            yield ('handler', self._handler)

    def bind(self, raw):
        """Return an Arg for the given raw value.

        As with match_type(), if the value is not supported by this
        parameter return None.
        """
        handler = self.match_type(raw)
        if handler is None:
            return None
        return Arg(self, raw, handler)

    def match_type(self, raw):
        """Return the datatype handler to use for the given raw value.

        If the value does not match then return None.
        """
        return self._handler


class DatatypeHandler(_ParameterBase):
    """Base class for datatype handlers."""

    def coerce(self, raw):
        """Return the deserialized equivalent of the given raw value."""
        # By default this is a noop.
        return raw

    def validate(self, coerced):
        """Ensure that the already-deserialized value is correct."""
        # By default this is a noop.
        return

    def as_data(self, coerced):
        """Return a serialized equivalent of the given value.

        This method round-trips with the "coerce()" method.
        """
        # By default this is a noop.
        return coerced


class Arg(Readonly, WithRepr):
    """The bridge between a raw value and a deserialized one.

    This is primarily the product of Parameter.bind().
    """
    # The value of this type lies in encapsulating intermediate state
    # and in caching data.

    def __init__(self, param, value, handler=None, israw=True):
        if not isinstance(param, Parameter):
            raise TypeError(
                'bad param (expected Parameter, got {!r})'.format(param))
        if handler is None:
            if israw:
                handler = param.match_type(value)
            else:
                raise TypeError('missing handler')
        if not isinstance(handler, DatatypeHandler):
            msg = 'bad handler (expected DatatypeHandler, got {!r})'
            raise TypeError(msg.format(handler))

        key = '_raw' if israw else '_value'
        kwargs = {key: value}
        self._bind_attrs(
            param=param,
            _handler=handler,
            _validated=False,
            **kwargs
        )

    def _init_args(self):
        yield ('param', self.param)
        israw = True
        try:
            yield ('value', self._raw)
        except AttributeError:
            yield ('value', self._value)
            israw = False
        if self.datatype != self.param.datatype:
            yield ('handler', self._handler)
        if not israw:
            yield ('israw', False)

    def __hash__(self):
        try:
            return hash(self.datatype)
        except TypeError:
            return hash(id(self))

    def __eq__(self, other):
        if type(self) is not type(other):
            return False
        if self.param != other.param:
            return False
        return self._as_data() == other._as_data()

    def __ne__(self, other):
        return not (self == other)

    @property
    def datatype(self):
        return self._handler.datatype

    @property
    def raw(self):
        """The serialized value."""
        return self.as_data()

    @property
    def value(self):
        """The de-serialized value."""
        value = self.coerce()
        if not self._validated:
            self._validate()
        return value

    def coerce(self, cached=True):
        """Return the deserialized equivalent of the raw value."""
        if not cached:
            try:
                raw = self._raw
            except AttributeError:
                # Use the cached value anyway.
                return self._value
            else:
                return self._handler.coerce(raw)

        try:
            return self._value
        except AttributeError:
            value = self._handler.coerce(self._raw)
            self._bind_attrs(
                _value=value,
            )
            return value

    def validate(self, force=False):
        """Ensure that the (deserialized) value is correct.

        If the value has a "validate()" method then it gets called.
        Otherwise it's up to the handler.
        """
        if not self._validated or force:
            self.coerce()
            self._validate()

    def _validate(self):
        try:
            validate = self._value.validate
        except AttributeError:
            self._handler.validate(self._value)
        else:
            validate()
        self._bind_attrs(
            _validated=True,
        )

    def as_data(self, cached=True):
        """Return a serialized equivalent of the value."""
        self.validate()
        if not cached:
            return self._handler.as_data(self._value)
        return self._as_data()

    def _as_data(self):
        try:
            return self._raw
        except AttributeError:
            try:
                as_data = self._value.as_data
            except AttributeError:
                as_data = self._handler.as_data
            raw = as_data(self._value)
            self._bind_attrs(
                _raw=raw,
            )
            return raw
