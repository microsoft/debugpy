from collections import namedtuple
from collections.abc import Sequence

from debugger_protocol._base import Readonly
from ._common import sentinel, NOT_SET, ANY, SIMPLE_TYPES


REF = '<ref>'
TYPE_REFERENCE = sentinel('TYPE_REFERENCE')


def _is_simple(datatype):
    if datatype is ANY:
        return True
    elif datatype in list(SIMPLE_TYPES):
        return True
    elif isinstance(datatype, Enum):
        return True
    else:
        return False


def _normalize_datatype(datatype):
    cls = type(datatype)
    if datatype == REF or datatype is TYPE_REFERENCE:
        return TYPE_REFERENCE
    elif datatype is ANY:
        return ANY
    elif datatype in list(SIMPLE_TYPES):
        return datatype
    elif isinstance(datatype, Enum):
        return datatype
    elif isinstance(datatype, Union):
        return datatype
    elif isinstance(datatype, Array):
        return datatype
    elif cls is set or cls is frozenset:
        return Union(*datatype)
    elif cls is list or cls is tuple:
        datatype, = datatype
        return Array(datatype)
    elif cls is dict:
        raise NotImplementedError
    else:
        return datatype


def _transform_datatype(datatype, op):
    try:
        dt_traverse = datatype.traverse
    except AttributeError:
        pass
    else:
        datatype = dt_traverse(lambda dt: _transform_datatype(dt, op))
    return op(datatype)


def _replace_ref(datatype, target):
    if datatype is TYPE_REFERENCE:
        return target
    else:
        return datatype


class Enum(namedtuple('Enum', 'datatype choice')):
    """A simple type with a limited set of allowed values."""

    @classmethod
    def _check_choice(cls, datatype, choice, strict=True):
        if callable(choice):
            return choice

        if isinstance(choice, str):
            msg = 'bad choice (expected {!r} values, got {!r})'
            raise ValueError(msg.format(datatype, choice))

        choice = frozenset(choice)
        if not choice:
            raise TypeError('missing choice')
        if not strict:
            return choice

        for value in choice:
            if type(value) is not datatype:
                msg = 'bad choice (expected {!r} values, got {!r})'
                raise ValueError(msg.format(datatype, choice))
        return choice

    def __new__(cls, datatype, choice, **kwargs):
        strict = kwargs.pop('strict', True)
        normalize = kwargs.pop('_normalize', True)
        (lambda: None)(**kwargs)  # Make sure there aren't any other kwargs.

        if not isinstance(datatype, type):
            raise ValueError('expected a class, got {!r}'.format(datatype))
        if datatype not in list(SIMPLE_TYPES):
            msg = 'only simple datatypes are supported, got {!r}'
            raise ValueError(msg.format(datatype))
        if normalize:
            # There's no need to normalize datatype (it's a simple type).
            pass
        choice = cls._check_choice(datatype, choice, strict=strict)

        self = super(Enum, cls).__new__(cls, datatype, choice)
        return self


class Union(tuple):
    """Declare a union of different types.

    The declared order is preserved and respected.

    Sets and frozensets are treated Unions in declarations.
    """

    @classmethod
    def _traverse(cls, datatypes, op):
        changed = False
        result = []
        for datatype in datatypes:
            transformed = op(datatype)
            if transformed is not datatype:
                changed = True
            result.append(transformed)
        return result, changed

    def __new__(cls, *datatypes, **kwargs):
        normalize = kwargs.pop('_normalize', True)
        (lambda: None)(**kwargs)  # Make sure there aren't any other kwargs.

        datatypes = list(datatypes)
        if normalize:
            datatypes, _ = cls._traverse(
                datatypes,
                lambda dt: _transform_datatype(dt, _normalize_datatype),
            )
        self = super(Union, cls).__new__(cls, datatypes)
        self._simple = all(_is_simple(dt) for dt in datatypes)
        return self

    def __repr__(self):
        return '{}{}'.format(type(self).__name__, tuple(self))

    def __hash__(self):
        return super(Union, self).__hash__()

    def __eq__(self, other):  # honors order
        if not isinstance(other, Union):
            return NotImplemented
        if super(Union, self).__eq__(other):
            return True
        if set(self) != set(other):
            return False
        if self._simple and other._simple:
            return True
        return NotImplemented

    def __ne__(self, other):
        return not (self == other)

    @property
    def datatypes(self):
        return set(self)

    def traverse(self, op, **kwargs):
        """Return a copy with op applied to each contained datatype."""
        datatypes, changed = self._traverse(self, op)
        if not changed and not kwargs:
            return self
        return self.__class__(*datatypes, **kwargs)


class Array(Readonly):
    """Declare an array (of a single type).

    Lists and tuples (single-item) are treated equivalently
    in declarations.
    """

    def __init__(self, itemtype, _normalize=True):
        if _normalize:
            itemtype = _normalize_datatype(itemtype)
        self._bind_attrs(
            itemtype=itemtype,
        )

    def __repr__(self):
        return '{}(datatype={!r})'.format(type(self).__name__, self.itemtype)

    def __hash__(self):
        return hash(self.itemtype)

    def __eq__(self, other):
        try:
            other_itemtype = other.itemtype
        except AttributeError:
            return False
        return self.itemtype == other_itemtype

    def __ne__(self, other):
        return not (self == other)

    def traverse(self, op, **kwargs):
        """Return a copy with op applied to the item datatype."""
        datatype = op(self.itemtype)
        if datatype is self.itemtype and not kwargs:
            return self
        return self.__class__(datatype, **kwargs)


class Field(namedtuple('Field', 'name datatype default optional')):
    """Declare a field in a data map param."""

    START_OPTIONAL = sentinel('START_OPTIONAL')

    def __new__(cls, name, datatype=str, enum=None, default=NOT_SET,
                optional=False, _normalize=True, **kwargs):
        if enum is not None and not isinstance(enum, Enum):
            datatype = Enum(datatype, enum)
            enum = None

        if _normalize:
            datatype = _normalize_datatype(datatype)
        self = super(Field, cls).__new__(
            cls,
            name=str(name) if name else None,
            datatype=datatype,
            default=default,
            optional=bool(optional),
        )
        self._kwargs = kwargs.items()
        return self

    @property
    def kwargs(self):
        return dict(self._kwargs)

    def traverse(self, op, **kwargs):
        """Return a copy with op applied to the datatype."""
        datatype = op(self.datatype)
        if datatype is self.datatype and not kwargs:
            return self
        kwargs.setdefault('default', self.default)
        kwargs.setdefault('optional', self.optional)
        return self.__class__(self.name, datatype, **kwargs)


class Fields(Readonly, Sequence):
    """Declare a set of fields."""

    @classmethod
    def _iter_fixed(cls, fields, _normalize=True):
        optional = None
        for field in fields or ():
            if field is Field.START_OPTIONAL:
                if optional is not None:
                    raise RuntimeError('START_OPTIONAL used more than once')
                optional = True
                continue

            if not isinstance(field, Field):
                raise TypeError('got non-field {!r}'.format(field))
            if _normalize:
                field = _transform_datatype(field, _normalize_datatype)
            if optional is not None and field.optional is not optional:
                field = field._replace(optional=optional)
            yield field

    def __init__(self, *fields, **kwargs):
        fields = list(self._iter_fixed(fields, **kwargs))
        self._bind_attrs(
            _fields=fields,
        )

    def __repr__(self):
        return '{}(*{})'.format(type(self).__name__, self._fields)

    def __hash__(self):
        return hash(tuple(self))

    def __eq__(self, other):
        try:
            other_len = len(other)
            other_iter = iter(other)
        except TypeError:
            return False
        if len(self) != other_len:
            return False
        for i, item in enumerate(other_iter):
            if self[i] != item:
                return False
        return True

    def __ne__(self, other):
        return not (self == other)

    def __len__(self):
        return len(self._fields)

    def __getitem__(self, index):
        return self._fields[index]

    def as_dict(self):
        return {field.name: field for field in self._fields}

    def traverse(self, op, **kwargs):
        """Return a copy with op applied to each field."""
        changed = False
        updated = []
        for field in self._fields:
            transformed = op(field)
            if transformed is not field:
                changed = True
            updated.append(transformed)

        if not changed and not kwargs:
            return self
        return self.__class__(*updated, **kwargs)
