# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import dataclasses
from collections.abc import Iterable, Mapping
from debugpy.common import log
from debugpy.server.inspect import ValueFormat
from debugpy.server.inspect.repr import formatted_repr
from itertools import count


class ChildObject:
    """
    Represents an object that is a child of another object that is accessible in some way.
    """

    value: object

    def __init__(self, value: object):
        self.value = value

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
        key_format = dataclasses.replace(format, max_length=format.max_length - 2)
        key_repr = formatted_repr(self.key, key_format)
        return f"[{key_repr}]"

    def expr(self, parent_expr: str) -> str:
        accessor = self.accessor(ValueFormat())
        return f"({parent_expr}){accessor}"


class ObjectInspector:
    """
    Inspects a generic object, providing access to its children (attributes, items etc).
    """

    value: object

    def __init__(self, value: object):
        self.value = value

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


class IterableInspector(ObjectInspector):
    value: Iterable

    def indexed_children(self) -> Iterable[IndexedChildObject]:
        yield from super().indexed_children()
        try:
            it = iter(self.value)
        except:
            return
        for i in count():
            try:
                item = next(it)
            except StopIteration:
                break
            except:
                log.exception("Error retrieving next item.")
                break
            yield IndexedChildObject(i, item)


class MappingInspector(ObjectInspector):
    value: Mapping

    def indexed_children(self) -> Iterable[IndexedChildObject]:
        yield from super().indexed_children()
        try:
            keys = self.value.keys()
        except:
            return
        it = iter(keys)
        while True:
            try:
                key = next(it)
            except StopIteration:
                break
            except:
                break
            try:
                value = self.value[key]
            except BaseException as exc:
                value = exc
            yield IndexedChildObject(key, value)


# Indexing str yields str, which is not very useful for debugging. What we want is to
# show the ordinal character values, similar to how it works for bytes & bytearray.
class StrInspector(IterableInspector):
    def indexed_children(self) -> Iterable[IndexedChildObject]:
        for i, ch in enumerate(self.value):
            yield IndexedChildObject(i, ord(ch))


def inspect_children(value: object) -> ObjectInspector:
    # TODO: proper extensible registry with public API for debugpy plugins.
    match value:
        case str():
            return StrInspector(value)
        case Mapping():
            return MappingInspector(value)
        case Iterable():
            return IterableInspector(value)
        case _:
            return ObjectInspector(value)
