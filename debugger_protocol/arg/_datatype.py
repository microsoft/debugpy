from debugger_protocol._base import Readonly, WithRepr
from ._common import NOT_SET, ANY, SIMPLE_TYPES
from ._decl import (
    _transform_datatype, _replace_ref,
    Enum, Union, Array, Field, Fields)
from ._errors import ArgTypeMismatchError, ArgMissingError, IncompleteArgError


def _coerce(datatype, value, call=True):
    if datatype is ANY:
        return value
    elif type(value) is datatype:
        return value
    elif value is datatype:
        return value
    elif datatype is None:
        pass  # fail below
    elif datatype in SIMPLE_TYPES:
        # We already checked for exact type match above.
        pass  # fail below

    # decl types
    elif isinstance(datatype, Enum):
        value = _coerce(datatype.datatype, value, call=False)
        if value in datatype.choice:
            return value
    elif isinstance(datatype, Union):
        for dt in datatype:
            try:
                return _coerce(dt, value, call=False)
            except ArgTypeMismatchError:
                continue
        else:
            raise ArgTypeMismatchError(value)
    elif isinstance(datatype, Array):
        try:
            values = iter(value)
        except TypeError:
            raise ArgTypeMismatchError(value)
        return [_coerce(datatype.itemtype, v, call=False)
                for v in values]
    elif isinstance(datatype, Field):
        return _coerce(datatype.datatype, value)
    elif isinstance(datatype, Fields):
        class ArgNamespace(FieldsNamespace):
            FIELDS = datatype

        return _coerce(ArgNamespace, value)
    elif issubclass(datatype, FieldsNamespace):
        arg = datatype.bind(value)
        try:
            arg_coerce = arg.coerce
        except AttributeError:
            return arg
        else:
            return arg_coerce()

    # fallbacks
    elif callable(datatype) and call:
        try:
            return datatype(value)
        except ArgTypeMismatchError:
            raise
        except (TypeError, ValueError):
            raise ArgTypeMismatchError(value)
    elif value == datatype:
        return value

    raise ArgTypeMismatchError(value)


########################
# fields

class FieldsNamespace(Readonly, WithRepr):
    """A namespace of field values exposed via attributes."""

    FIELDS = None
    PARAM_TYPE = None
    PARAM = None

    @classmethod
    def traverse(cls, op, **kwargs):
        """Apply op to each field in cls.FIELDS."""
        fields = cls._normalize(cls.FIELDS)
        fields = fields.traverse(op)
        cls.FIELDS = cls._normalize(fields)
        return cls

    @classmethod
    def normalize(cls, *transforms):
        """Normalize FIELDS and apply the given ops."""
        fields = cls._normalize(cls.FIELDS)
        if not isinstance(fields, Fields):
            fields = Fields(*fields)
        for transform in transforms:
            fields = _transform_datatype(fields, transform)
            fields = cls._normalize(fields)
        cls.FIELDS = fields
        return cls

    @classmethod
    def _normalize(cls, fields):
        if fields is None:
            raise TypeError('missing FIELDS')
        if isinstance(fields, Fields):
            try:
                normalized = cls._normalized
            except AttributeError:
                normalized = cls._normalized = False
        else:
            fields = Fields(*fields)
            normalized = cls._normalized = False
        if not normalized:
            fields = _transform_datatype(fields,
                                         lambda dt: _replace_ref(dt, cls))
        return fields

    @classmethod
    def bind(cls, ns, **kwargs):
        if isinstance(ns, cls):
            return ns
        param = cls.PARAM
        if param is None:
            if cls.PARAM_TYPE is None:
                return cls(**ns)
            param = cls.PARAM_TYPE(cls.FIELDS, cls)
        return param.bind(ns, **kwargs)

    @classmethod
    def _bind(cls, kwargs):
        cls.FIELDS = cls._normalize(cls.FIELDS)
        bound, missing = _fields_bind(cls.FIELDS, kwargs)
        if missing:
            raise IncompleteArgError(cls.FIELDS, missing)

        values = {}
        validators = []
        serializers = {}
        for field, arg in bound.items():
            if arg is NOT_SET:
                continue

            try:
                coerce = arg.coerce
            except AttributeError:
                value = arg
            else:
                value = coerce(arg)
            values[field.name] = value

            try:
                validate = arg.validate
                validate = value.validate
            except AttributeError:
                pass
            else:
                validators.append(validate)

            try:
                as_data = arg.as_data
                as_data = value.as_data
            except AttributeError:
                pass
            else:
                serializers[field.name] = as_data
        values['_validators'] = validators
        values['_serializers'] = serializers
        return values

    def __init__(self, **kwargs):
        super(FieldsNamespace, self).__init__()
        validate = kwargs.pop('_validate', True)

        kwargs = self._bind(kwargs)
        self._bind_attrs(**kwargs)
        if validate:
            self.validate()

    def _init_args(self):
        if self.FIELDS is not None:
            for field in self.FIELDS:
                try:
                    value = getattr(self, field.name)
                except AttributeError:
                    continue
                yield (field.name, value)
        else:
            for item in sorted(vars(self).items()):
                yield item

    def __eq__(self, other):
        try:
            other_as_data = other.as_data
        except AttributeError:
            other_data = other
        else:
            other_data = other_as_data()

        return self.as_data() == other_data

    def __ne__(self, other):
        return not (self == other)

    def validate(self):
        """Ensure that the field values are valid."""
        for validate in self._validators:
            validate()

    def as_data(self):
        """Return serializable data for the instance."""
        data = {name: as_data()
                for name, as_data in self._serializers.items()}
        for field in self.FIELDS:
            if field.name in data:
                continue
            try:
                data[field.name] = getattr(self, field.name)
            except AttributeError:
                pass
        return data


def _field_missing(field, value):
    if value is NOT_SET:
        return True

    try:
        missing = field.datatype.missing
    except AttributeError:
        return None
    else:
        return missing(value)


def _field_bind(field, value, applydefaults=True):
    missing = _field_missing(field, value)
    if missing:
        if field.optional:
            if applydefaults:
                return field.default
            return NOT_SET
        raise ArgMissingError(field, missing)

    try:
        bind = field.datatype.bind
    except AttributeError:
        bind = (lambda v: _coerce(field.datatype, v))
    return bind(value)


def _fields_iter_values(fields, remainder):
    for field in fields or ():
        value = remainder.pop(field.name, NOT_SET)
        yield field, value


def _fields_iter_bound(fields, remainder, applydefaults=True):
    for field, value in _fields_iter_values(fields, remainder):
        try:
            arg = _field_bind(field, value, applydefaults=applydefaults)
        except ArgMissingError as exc:
            yield field, value, exc, False
#        except ArgTypeMismatchError as exc:
#            yield field, value, None, exc
        else:
            yield field, arg, False, False


def _fields_bind(fields, kwargs, applydefaults=True):
    bound = {}
    missing = {}
    mismatched = {}
    remainder = dict(kwargs)
    bound_iter = _fields_iter_bound(fields, remainder,
                                    applydefaults=applydefaults)
    for field, arg, missed, mismatch in bound_iter:
        if missed:
            missing[field.name] = missed
        elif mismatch:
            mismatched[field.name] = arg
        else:
            bound[field] = arg
    if remainder:
        remainder = ', '.join(sorted(remainder))
        raise TypeError('got extra fields: {}'.format(remainder))
    if mismatched:
        raise ArgTypeMismatchError(mismatched)
    return bound, missing
