from ._common import NOT_SET, ANY, SIMPLE_TYPES
from ._datatype import FieldsNamespace
from ._decl import Enum, Union, Array, Mapping, Field, Fields
from ._errors import ArgTypeMismatchError
from ._param import Parameter, DatatypeHandler


#def as_parameter(cls):
#    """Return a parameter that wraps the given FieldsNamespace subclass."""
#    # XXX inject_params
#    cls.normalize(_inject_params)
#    param = param_from_datatype(cls)
##    cls.PARAM = param
#    return param
#
#
#def _inject_params(datatype):
#    return param_from_datatype(datatype)


def param_from_datatype(datatype, **kwargs):
    """Return a parameter for the given datatype."""
    if isinstance(datatype, Parameter):
        return datatype

    if isinstance(datatype, DatatypeHandler):
        return Parameter(datatype.datatype, datatype, **kwargs)
    elif isinstance(datatype, Fields):
        return ComplexParameter(datatype, **kwargs)
    elif isinstance(datatype, Field):
        return param_from_datatype(datatype.datatype, **kwargs)
    elif datatype is ANY:
        return NoopParameter()
    elif datatype is None:
        return SingletonParameter(None)
    elif datatype in list(SIMPLE_TYPES):
        return SimpleParameter(datatype, **kwargs)
    elif isinstance(datatype, Enum):
        return EnumParameter(datatype.datatype, datatype.choice, **kwargs)
    elif isinstance(datatype, Union):
        return UnionParameter(datatype, **kwargs)
    elif isinstance(datatype, (set, frozenset)):
        return UnionParameter(Union(*datatype), **kwargs)
    elif isinstance(datatype, Array):
        return ArrayParameter(datatype, **kwargs)
    elif isinstance(datatype, (list, tuple)):
        datatype, = datatype
        return ArrayParameter(Array(datatype), **kwargs)
    elif not isinstance(datatype, type):
        raise NotImplementedError
    elif issubclass(datatype, FieldsNamespace):
        param = datatype.param()
        return param or ComplexParameter(datatype, **kwargs)
    else:
        raise NotImplementedError


########################
# param types

class NoopParameter(Parameter):
    """A parameter that treats any value as-is."""
    def __init__(self):
        handler = DatatypeHandler(ANY)
        super(NoopParameter, self).__init__(ANY, handler)


NOOP = NoopParameter()


class SingletonParameter(Parameter):
    """A parameter that works only for the given value."""

    class HANDLER(DatatypeHandler):
        def validate(self, coerced):
            if coerced is not self.datatype:
                raise ValueError(
                    'expected {!r}, got {!r}'.format(self.datatype, coerced))

    def __init__(self, obj):
        handler = self.HANDLER(obj)
        super(SingletonParameter, self).__init__(obj, handler)

    def match_type(self, raw):
        # Note we do not check equality for singletons.
        if raw is not self.datatype:
            return None
        return super(SingletonParameter, self).match_type(raw)


class SimpleHandler(DatatypeHandler):
    """A datatype handler for basic value types."""

    def __init__(self, cls):
        if not isinstance(cls, type):
            raise ValueError('expected a class, got {!r}'.format(cls))
        super(SimpleHandler, self).__init__(cls)

    def coerce(self, raw):
        if type(raw) is self.datatype:
            return raw
        return self.datatype(raw)

    def validate(self, coerced):
        if type(coerced) is not self.datatype:
            raise ValueError(
                'expected {!r}, got {!r}'.format(self.datatype, coerced))


class SimpleParameter(Parameter):
    """A parameter for basic value types."""

    HANDLER = SimpleHandler

    def __init__(self, cls, strict=True):
        handler = self.HANDLER(cls)
        super(SimpleParameter, self).__init__(cls, handler)
        self._strict = strict

    def match_type(self, raw):
        if self._strict:
            if type(raw) is not self.datatype:
                return None
        elif not isinstance(raw, self.datatype):
            return None
        return super(SimpleParameter, self).match_type(raw)


class EnumParameter(Parameter):
    """A parameter for enums of basic value types."""

    class HANDLER(SimpleHandler):

        def __init__(self, cls, enum):
            if not enum:
                raise TypeError('missing enum')
            super(EnumParameter.HANDLER, self).__init__(cls)
            if not callable(enum):
                enum = set(enum)
            self.enum = enum

        def validate(self, coerced):
            super(EnumParameter.HANDLER, self).validate(coerced)

            if not self._match_enum(coerced):
                msg = 'expected one of {!r}, got {!r}'
                raise ValueError(msg.format(self.enum, coerced))

        def _match_enum(self, coerced):
            if callable(self.enum):
                if not self.enum(coerced):
                    return False
            elif coerced not in self.enum:
                return False
            return True

    def __init__(self, cls, enum):
        handler = self.HANDLER(cls, enum)
        super(EnumParameter, self).__init__(cls, handler)
        self._match_enum = handler._match_enum

    def match_type(self, raw):
        if type(raw) is not self.datatype:
            return None
        if not self._match_enum(raw):
            return None
        return super(EnumParameter, self).match_type(raw)


class UnionParameter(Parameter):
    """A parameter that supports multiple different types."""

    HANDLER = None  # no handler

    @classmethod
    def from_datatypes(cls, *datatypes, **kwargs):
        datatype = Union(*datatypes)
        return cls(datatype, **kwargs)

    def __init__(self, datatype, **kwargs):
        if not isinstance(datatype, Union):
            raise ValueError('expected Union, got {!r}'.format(datatype))
        super(UnionParameter, self).__init__(datatype)

        choice = []
        for dt in datatype:
            param = param_from_datatype(dt)
            choice.append(param)
        self.choice = choice

    def __eq__(self, other):
        if type(self) is not type(other):
            return False
        return set(self.datatype) == set(other.datatype)

    def match_type(self, raw):
        for param in self.choice:
            handler = param.match_type(raw)
            if handler is not None:
                return handler
        return None


class ArrayParameter(Parameter):
    """A parameter that is a list of some fixed type."""

    class HANDLER(DatatypeHandler):

        def __init__(self, datatype, handlers=None, itemparam=None):
            if not isinstance(datatype, Array):
                raise ValueError(
                    'expected an Array, got {!r}'.format(datatype))
            super(ArrayParameter.HANDLER, self).__init__(datatype)
            self.handlers = handlers
            self.itemparam = itemparam

        def coerce(self, raw):
            if self.handlers is None:
                if self.itemparam is None:
                    itemtype = self.datatype.itemtype
                    self.itemparam = param_from_datatype(itemtype)
                handlers = []
                for item in raw:
                    handler = self.itemparam.match_type(item)
                    if handler is None:
                        raise ArgTypeMismatchError(item)
                    handlers.append(handler)
                self.handlers = handlers

            result = []
            for i, item in enumerate(raw):
                handler = self.handlers[i]
                item = handler.coerce(item)
                result.append(item)
            return result

        def validate(self, coerced):
            if self.handlers is None:
                raise TypeError('coerce first')
            for i, item in enumerate(coerced):
                handler = self.handlers[i]
                handler.validate(item)

        def as_data(self, coerced):
            if self.handlers is None:
                raise TypeError('coerce first')
            data = []
            for i, item in enumerate(coerced):
                handler = self.handlers[i]
                datum = handler.as_data(item)
                data.append(datum)
            return data

    @classmethod
    def from_itemtype(cls, itemtype, **kwargs):
        datatype = Array(itemtype)
        return cls(datatype, **kwargs)

    def __init__(self, datatype):
        if not isinstance(datatype, Array):
            raise ValueError('expected Array, got {!r}'.format(datatype))
        itemparam = param_from_datatype(datatype.itemtype)
        handler = self.HANDLER(datatype, None, itemparam)
        super(ArrayParameter, self).__init__(datatype, handler)

        self.itemparam = itemparam

    def match_type(self, raw):
        if not isinstance(raw, list):
            return None
        handlers = []
        for item in raw:
            handler = self.itemparam.match_type(item)
            if handler is None:
                return None
            handlers.append(handler)
        return self.HANDLER(self.datatype, handlers)


class MappingParameter(Parameter):
    """A parameter that is a mapping of some fixed type."""

    class HANDLER(DatatypeHandler):

        def __init__(self, datatype, handlers=None,
                     keyparam=None, valueparam=None):
            if not isinstance(datatype, Mapping):
                raise ValueError(
                    'expected an Mapping, got {!r}'.format(datatype))
            super(MappingParameter.HANDLER, self).__init__(datatype)
            self.handlers = handlers
            self.keyparam = keyparam
            self.valueparam = valueparam

        def coerce(self, raw):
            if self.handlers is None:
                if self.keyparam is None:
                    keytype = self.datatype.keytype
                    self.keyparam = param_from_datatype(keytype)
                if self.valueparam is None:
                    valuetype = self.datatype.valuetype
                    self.valueparam = param_from_datatype(valuetype)
                handlers = {}
                for key, value in raw.items():
                    keyhandler = self.keyparam.match_type(key)
                    if keyhandler is None:
                        raise ArgTypeMismatchError(key)
                    valuehandler = self.valueparam.match_type(value)
                    if valuehandler is None:
                        raise ArgTypeMismatchError(value)
                    handlers[key] = (keyhandler, valuehandler)
                self.handlers = handlers

            result = {}
            for key, value in raw.items():
                keyhandler, valuehandler = self.handlers[key]
                key = keyhandler.coerce(key)
                value = valuehandler.coerce(value)
                result[key] = value
            return result

        def validate(self, coerced):
            if self.handlers is None:
                raise TypeError('coerce first')
            for key, value in coerced.items():
                keyhandler, valuehandler = self.handlers[key]
                keyhandler.validate(key)
                valuehandler.validate(value)

        def as_data(self, coerced):
            if self.handlers is None:
                raise TypeError('coerce first')
            data = {}
            for key, value in coerced.items():
                keyhandler, valuehandler = self.handlers[key]
                key = keyhandler.as_data(key)
                value = valuehandler.as_data(value)
                data[key] = value
            return data

    @classmethod
    def from_valuetype(cls, valuetype, keytype=str, **kwargs):
        datatype = Mapping(valuetype, keytype)
        return cls(datatype, **kwargs)

    def __init__(self, datatype):
        if not isinstance(datatype, Mapping):
            raise ValueError('expected Mapping, got {!r}'.format(datatype))
        keyparam = param_from_datatype(datatype.keytype)
        valueparam = param_from_datatype(datatype.valuetype)
        handler = self.HANDLER(datatype, None, keyparam, valueparam)
        super(MappingParameter, self).__init__(datatype, handler)

        self.keyparam = keyparam
        self.valueparam = valueparam

    def match_type(self, raw):
        if not isinstance(raw, dict):
            return None
        handlers = {}
        for key, value in raw.items():
            keyhandler = self.keyparam.match_type(key)
            if keyhandler is None:
                return None
            valuehandler = self.valueparam.match_type(value)
            if valuehandler is None:
                return None
            handlers[key] = (keyhandler, valuehandler)
        return self.HANDLER(self.datatype, handlers)


class ComplexParameter(Parameter):

    class HANDLER(DatatypeHandler):

        def __init__(self, datatype, handlers=None):
            if (type(datatype) is not type or
                not issubclass(datatype, FieldsNamespace)
                ):
                msg = 'expected FieldsNamespace, got {!r}'
                raise ValueError(msg.format(datatype))
            super(ComplexParameter.HANDLER, self).__init__(datatype)
            self.handlers = handlers

        def coerce(self, raw):
            if self.handlers is None:
                fields = self.datatype.FIELDS.as_dict()
                handlers = {}
                for name, value in raw.items():
                    param = param_from_datatype(fields[name])
                    handler = param.match_type(value)
                    if handler is None:
                        raise ArgTypeMismatchError((name, value))
                    handlers[name] = handler
                self.handlers = handlers

            result = {}
            for name, value in raw.items():
                handler = self.handlers[name]
                value = handler.coerce(value)
                result[name] = value
            return self.datatype(**result)

        def validate(self, coerced):
            if self.handlers is None:
                raise TypeError('coerce first')
            for field in self.datatype.FIELDS:
                try:
                    value = getattr(coerced, field.name)
                except AttributeError:
                    continue
                handler = self.handlers[field.name]
                handler.validate(value)

        def as_data(self, coerced):
            if self.handlers is None:
                raise TypeError('coerce first')
            data = {}
            for field in self.datatype.FIELDS:
                try:
                    value = getattr(coerced, field.name)
                except AttributeError:
                    continue
                handler = self.handlers[field.name]
                datum = handler.as_data(value)
                data[field.name] = datum
            return data

    def __init__(self, datatype):
        if isinstance(datatype, Fields):
            class ArgNamespace(FieldsNamespace):
                FIELDS = datatype

            datatype = ArgNamespace
        elif (type(datatype) is not type or
              not issubclass(datatype, FieldsNamespace)):
            msg = 'expected Fields or FieldsNamespace, got {!r}'
            raise ValueError(msg.format(datatype))
        datatype.normalize()
        datatype.PARAM = self
        # We set handler later in match_type().
        super(ComplexParameter, self).__init__(datatype)

        self.params = {field.name: param_from_datatype(field)
                       for field in datatype.FIELDS}

    def __eq__(self, other):
        if super(ComplexParameter, self).__eq__(other):
            return True
        try:
            fields = self._datatype.FIELDS
            other_fields = other._datatype.FIELDS
        except AttributeError:
            return NotImplemented
        else:
            return fields == other_fields

    def match_type(self, raw):
        if not isinstance(raw, dict):
            return None
        handlers = {}
        for field in self.datatype.FIELDS:
            try:
                value = raw[field.name]
            except KeyError:
                if not field.optional:
                    return None
                value = field.default
                if value is NOT_SET:
                    continue
            param = self.params[field.name]
            handler = param.match_type(value)
            if handler is None:
                return None
            handlers[field.name] = handler
        return self.HANDLER(self.datatype, handlers)
