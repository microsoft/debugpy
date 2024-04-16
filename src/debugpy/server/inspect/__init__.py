# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

"""
Object inspection: rendering values, enumerating children etc.

This module provides a generic non-DAP-aware API with minimal dependencies, so that
it can be unit-tested in isolation without requiring a live debugpy session.

debugpy.server.eval then wraps it in DAP-specific adapter classes that expose the
same functionality in DAP terms.
"""

import io
import sys
from array import array
from collections import deque
from collections.abc import Iterable, Mapping
from typing import Optional


class ValueFormat:
    hex: bool
    """Whether integers should be rendered in hexadecimal."""

    max_length: int
    """
    Maximum length of the string representation of variable values, including values
    of indices returned by IndexedChildObject.accessor().
    """

    truncation_suffix: str
    """Suffix to append to truncated string representations; counts towards max_length."""

    circular_ref_marker: Optional[str]
    """
    String to use for nested circular references (e.g. list containing itself). If None,
    circular references aren't detected and the caller is responsible for avoiding them
    in inputs.
    """

    def __init__(
        self,
        *,
        hex: bool = False,
        max_length: int = sys.maxsize,
        truncation_suffix: str = "",
        circular_ref_marker: Optional[str] = None,
    ):
        assert max_length >= len(truncation_suffix)
        self.hex = hex
        self.max_length = max_length
        self.truncation_suffix = truncation_suffix
        self.circular_ref_marker = circular_ref_marker


class ChildObject:
    """
    Represents an object that is a child of another object that is accessible in some way.
    """

    value: object

    def __init__(self, value: object):
        self.value = value
        self.format = format

    def accessor(self, format: ValueFormat) -> str:
        """
        Accessor used to retrieve this object.

        This is a display string and is not intended to be used for eval, but it should
        generally correlate to the expression that can be used to retrieve the object in
        some clear and obvious way. Some examples of accessors:

            "attr"  - value.attr
            "[key]" - value[key]
            "len()" - len(value)
        """
        raise NotImplementedError

    def expr(self, parent_expr: str) -> str:
        """
        Returns an expression that can be used to retrieve this object from its parent,
        given the expression to compute the parent.
        """
        raise NotImplementedError


class NamedChildObject(ChildObject):
    """
    Child object that has a predefined accessor used to access it.

    This includes not just attributes, but all children that do not require repr() of
    index, key etc to compute the accessor.
    """

    def __init__(self, name: str, value: object):
        super().__init__(value)
        self.name = name

    def accessor(self, format: ValueFormat) -> str:
        return self.name

    def expr(self, parent_expr: str) -> str:
        accessor = self.accessor(ValueFormat())
        return f"({parent_expr}).{accessor}"


class LenChildObject(NamedChildObject):
    """
    A synthetic child object that represents the return value of len().
    """

    def __init__(self, parent: object):
        super().__init__("len()", len(parent))

    def expr(self, parent_expr: str) -> str:
        return f"len({parent_expr})"


class IndexedChildObject(ChildObject):
    """
    Child object that has a computed accessor.
    """

    key: object

    def __init__(self, key: object, value: object):
        super().__init__(value)
        self.key = key
        self.indexer = None

    def accessor(self, format: ValueFormat) -> str:
        key_repr = inspect(self.key, format).repr()
        return f"[{key_repr}]"

    def expr(self, parent_expr: str) -> str:
        accessor = self.accessor(ValueFormat())
        return f"({parent_expr}){accessor}"


# TODO: break apart into separate classes for child inspection and for repr, because these
# don't necessarily match. For example, if a user-defined class is derived from dict, the
# protocol to retrieve the children is still the same, so the same inspector should be used
# for it. However, its repr will likely be different, and if we use the dict inspector for
# any subclass of dict, we'll get this wrong. This matters when editing variable values,
# since repr of the value provides the initial text for the user to edit. So if we show a
# dict repr for a subclass, and user clicks edit and then saves, the value will be silently
# replaced with a plain dict.
class ObjectInspector:
    """
    Inspects a generic object, providing access to its string representation and children.
    """

    class ReprContext:
        """
        Context for ObjectInspector.iter_repr().
        """

        format: ValueFormat

        chars_remaining: int
        """
        How many more characters are allowed in the output.

        Implementations of ObjectInspector.iter_repr() can use this to optimize by yielding
        larger chunks if there is enough space left for them.
        """

        path: list[object]
        """
        Path to the current object being inspected, starting from the root object on which
        repr() was called, with each new element corresponding to a single nest() call.
        """

        def __init__(self, inspector: "ObjectInspector"):
            self.format = inspector.format
            self.chars_remaining = self.format.max_length
            self.path = []

        def nest(self, value: object):
            circular_ref_marker = self.format.circular_ref_marker
            if circular_ref_marker is not None and any(x is value for x in self.path):
                yield circular_ref_marker
                return

            self.path.append(value)
            try:
                yield from inspect(value, self.format).iter_repr(self)
            finally:
                self.path.pop()

    value: object
    format: ValueFormat

    def __init__(self, value: object, format: ValueFormat):
        self.value = value
        self.format = format

    def children(self) -> Iterable[ChildObject]:
        yield from self.named_children()
        yield from self.indexed_children()

    def indexed_children_count(self) -> int:
        try:
            return len(self.value)
        except:
            return 0

    def indexed_children(self) -> Iterable[IndexedChildObject]:
        return ()

    def named_children_count(self) -> int:
        return len(tuple(self.named_children()))

    def named_children(self) -> Iterable[NamedChildObject]:
        def attrs():
            try:
                names = dir(self.value)
            except:
                names = ()

            # TODO: group class/instance/function/special
            for name in names:
                if name.startswith("__"):
                    continue
                try:
                    value = getattr(self.value, name)
                except BaseException as exc:
                    value = exc
                try:
                    if hasattr(value, "__call__"):
                        continue
                except:
                    pass
                yield NamedChildObject(name, value)

            try:
                yield LenChildObject(self.value)
            except:
                pass

        return sorted(attrs(), key=lambda var: var.name)

    def repr(self) -> str:
        """
        repr() of the inspected object. Like builtins.repr(), but with additional
        formatting options and size limit.
        """
        context = self.ReprContext(self)
        output = io.StringIO()
        for chunk in context.nest(self.value):
            output.write(chunk)
            context.chars_remaining -= len(chunk)
            if context.chars_remaining < 0:
                output.seek(self.format.max_length - len(self.format.truncation_suffix))
                output.truncate()
                output.write(self.format.truncation_suffix)
                break
        return output.getvalue()

    def iter_repr(self, context: ReprContext) -> Iterable[str]:
        """
        Streaming repr of the inspected object. Like builtins.repr(), but instead
        of computing and returning the whole string right away, returns an iterator
        that yields chunks of the repr as they are computed.

        When object being inspected contains other objects that it needs to include
        in its own repr, it should pass the nested objects to context.nest() and
        yield from the returned iterator. This will dispatch the nested repr to the
        correct inspector, and make sure that context.nesting_level is updated as
        needed while nested repr is being computed.

        When possible, implementations should use context.chars_remaining as a hint
        to yield larger chunks. However, there is no obligation for iter_repr() to
        yield chunks smaller than chars_remaining.

        The default implementation delegates to builtins.repr(), which will always
        produce the correct result, but without any streaming. Derived inspectors
        should always override this method to stream repr if possible.
        """
        try:
            result = repr(self.value)
        except BaseException as exc:
            try:
                result = f"<repr() error: {exc}>"
            except:
                result = "<repr() error>"
        yield result


def inspect(value: object, format: ValueFormat) -> ObjectInspector:
    from debugpy.server.inspect import stdlib

    # TODO: proper extensible registry with public API for debugpy plugins.
    def get_inspector():
        # TODO: should subtypes of standard collections be treated the same? This works
        # for fetching items, but gets repr() wrong - might have to split the two.
        match value:
            case int():
                return stdlib.IntInspector
            case str():
                return stdlib.StrInspector
            case bytes():
                return stdlib.BytesInspector
            case bytearray():
                return stdlib.ByteArrayInspector
            case tuple():
                return stdlib.TupleInspector
            case list():
                return stdlib.ListInspector
            case set():
                return stdlib.SetInspector
            case frozenset():
                return stdlib.FrozenSetInspector
            case array():
                return stdlib.ArrayInspector
            case deque():
                return stdlib.DequeInspector
            case dict():
                return stdlib.DictInspector
            case Mapping():
                return stdlib.MappingInspector
            case Iterable():
                return stdlib.IterableInspector
            case _:
                return ObjectInspector

    return get_inspector()(value, format)
