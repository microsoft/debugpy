
class ArgumentError(TypeError):
    """The base class for argument-related exceptions."""


class ArgMissingError(ArgumentError):
    """Indicates that the argument for the field is missing."""

    def __init__(self, field):
        super(ArgMissingError, self).__init__(
            'missing arg {!r}'.format(field.name))
        self.field = field


class IncompleteArgError(ArgumentError):
    """Indicates that the "complex" arg has missing fields."""

    def __init__(self, fields, missing):
        msg = 'incomplete arg (missing or incomplete fields: {})'
        super(IncompleteArgError, self).__init__(
            msg.format(', '.join(sorted(missing))))
        self.fields = fields
        self.missing = missing


class ArgTypeMismatchError(ArgumentError):
    """Indicates that the arg did not have the expected type."""

    def __init__(self, value):
        super(ArgTypeMismatchError, self).__init__(
            'bad value {!r} (unsupported type)'.format(value))
        self.value = value
