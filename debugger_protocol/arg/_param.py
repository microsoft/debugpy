from debugger_protocol._base import Readonly, WithRepr
from ._common import NOT_SET


#def arg_missing(param, raw):
#    """Return True if the value is "missing" relative to the parameter.
#
#    The result is based on the result of calling param.missing(), with
#    the exception of if the value is NOT_SET (which always means
#    "missing").
#    """
#    if raw is NOT_SET:
#        return True
#    param = param.match_type(raw)
#    missing = param.missing(raw)
#    if missing:
#        return missing
#    elif missing is None:
#        return True
#    else:
#        return False


class Parameter(object):
    """Effectively a serializer for a "class" of values.

    The parameter is backed by one or more data classes to which
    raw values are de-serialized (and which serialize to the
    corresponding raw values).
    """

    def __init__(self, impl):
        if not isinstance(impl, ParameterImplBase):
            raise TypeError('bad impl')
        self._impl = impl

    def __repr__(self):
        return '<{} wrapping {!r}>'.format(type(self).__name__, self._impl)

    def __hash__(self):
        return hash(self._impl)

    def __eq__(self, other):
        if type(self) is not type(other):
            return False
        return self._impl == other._impl

    def __ne__(self, other):
        return not (self == other)

    def bind(self, raw):
        """Return an Arg for the given raw value.

        As with match_type(), if the value is not supported by this
        parameter return None.
        """
        param = self.match_type(raw)
        return Arg(param, raw)

    def match_type(self, raw):
        """Return the parameter to use for the given raw value.

        If the value does not match then return None.

        Normally this method returns self or None.  For some parameters
        the method may return other parameters to use.  In fact, for
        some (e.g. unions) it only returns other parameters (never
        returns self).
        """
        param = self._impl.match_type(raw)
        if param is None:
            return None
        elif param is self._impl:
            return self
        elif isinstance(param, Parameter):
            return param
        else:
            return self.__class__(param)

    def missing(self, raw):
        """Return True if the raw value should be treated as NOT_SET.

        A True result corresponds to raising ArgMissingError.  A result
        of None means defer to other parameters, much as NotImplemented
        works.  If every parameter returns None then the value should
        be treated as missing.

        In addition to True/False, for "complex" values missing() may
        also return a mapping of names to the portions of the raw value
        that are missing.  In that case the result corresponds instead
        to raising IncompleteArgError.
        """
        return self._impl.missing(raw)

    def coerce(self, raw):
        # XXX
        """Return the deserialized equivalent of the given raw value.

        XXX

        If the parameter's underlying data class
        """
        return self._impl.coerce(raw)

    def validate(self, coerced):
        """Ensure that the already-deserialized value is correct.

        If the value has a "validate()" method then it gets called.
        Otherwise it's up to the parameter.
        """
        try:
            validate = coerced.validate
        except AttributeError:
            self._impl.validate(coerced)
        else:
            validate()

    def as_data(self, coerced):
        """Return a serialized equivalent of the given value.

        This method round-trips with the "coerce()" method.
        """
        try:
            as_data = coerced.as_data
        except AttributeError:
            return self._impl.as_data(coerced)
        else:
            return as_data(coerced)


class ParameterImplBase(Readonly):
    """The base class for low-level Parameter implementations.

    The default methods are essentially noops.

    See corresponding Parameter methods.
    """

    def __init__(self, datatype=NOT_SET):
        self._bind_attrs(datatype=datatype)

    def __repr__(self):
        if self.datatype is NOT_SET:
            return '{}()'.format(type(self).__name__)
        else:
            return '{}({!r})'.format(type(self).__name__, self.datatype)

    def __hash__(self):
        try:
            return hash(self.datatype)
        except TypeError:
            return hash(id(self))

    def __eq__(self, other):
        if type(self) is not type(other):
            return False
        return self.datatype == other.datatype

    def __ne__(self, other):
        return not (self == other)

    def match_type(self, raw):
        return self

    def missing(self, raw):
        return False

    def coerce(self, raw):
        return raw

    def validate(self, coerced):
        return

    def as_data(self, coerced):
        return coerced


class Arg(Readonly, WithRepr):
    """The bridge between a raw value and a deserialized one.

    This is primarily the product of Parameter.bind().
    """
    # The value of this type lies in encapsulating intermediate state
    # and caching data.

    def __init__(self, param, value, israw=True):
        if isinstance(param, ParameterImplBase):
            param = Parameter(param)
        elif not isinstance(param, Parameter):
            raise TypeError(
                'bad param (expected Parameter, got {!r})'.format(param))
        key = '_raw' if israw else '_value'
        kwargs = {key: value}
        self._bind_attrs(
            param=param,
            _validated=False,
            **kwargs
        )

    def _init_args(self):
        yield ('param', self.param)
        try:
            yield ('value', self._raw)
        except AttributeError:
            yield ('value', self._value)
            yield ('israw', False)

    def __hash__(self):
        try:
            return hash(self.param.datatype)
        except TypeError:
            return hash(id(self))

    def __eq__(self, other):
        if type(self) is not type(other):
            return False
        return self.param == other.param

    def __ne__(self, other):
        return not (self == other)

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
                return self.param.coerce(raw)

        try:
            return self._value
        except AttributeError:
            value = self.param.coerce(self._raw)
            self._bind_attrs(
                _value=value,
            )
            return value

    def validate(self, force=False):
        """Ensure that the (deserialized) value is correct."""
        if not self._validated or force:
            self.coerce()
            self._validate()

    def _validate(self):
        self.param.validate(self._value)
        self._bind_attrs(
            _validated=True,
        )

    def as_data(self, cached=True):
        """Return a serialized equivalent of the value."""
        self.validate()
        if not cached:
            return self.param.as_data(self._value)

        try:
            return self._raw
        except AttributeError:
            raw = self.param.as_data(self._value)
            self._bind_attrs(
                _raw=raw,
            )
            return raw
