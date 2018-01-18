from debugger_protocol._base import Readonly, WithRepr


class Base(Readonly, WithRepr):
    """Base class for message-related types."""

    _INIT_ARGS = None

    @classmethod
    def from_data(cls, **kwargs):
        """Return an instance based on the given raw data."""
        return cls(**kwargs)

    def __init__(self):
        self._validate()

    def _validate(self):
        pass

    def as_data(self):
        """Return serializable data for the instance."""
        return {}
