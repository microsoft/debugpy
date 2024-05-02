import pytest
from debugpy.server.inspect import ValueFormat
from debugpy.server.inspect.children import NamedChildObject, inspect_children
from debugpy.server.inspect.repr import formatted_repr


@pytest.mark.parametrize("base", ["dec", "hex"])
@pytest.mark.parametrize("value", [0, 42, -42, 1_234_567_890_123, -1_234_567_890_123])
def test_int_repr(value, base):
    format = ValueFormat(hex=(base == "hex"))
    expected_repr = (hex if base == "hex" else repr)(value)
    assert formatted_repr(value, format) == expected_repr


def test_int_repr_derived():
    class CustomInt(int):
        def __repr__(self):
            return f"CustomInt({int(self)})"

    value = CustomInt(42)
    assert formatted_repr(value, ValueFormat()) == repr(value)


def test_int_children():
    inspector = inspect_children(42)

    assert inspector.indexed_children_count() == 0
    assert list(inspector.indexed_children()) == []

    assert inspector.named_children_count() == 4
    assert list(inspector.named_children()) == [
        NamedChildObject("denominator", 1),
        NamedChildObject("imag", 0),
        NamedChildObject("numerator", 42),
        NamedChildObject("real", 42),
    ]
