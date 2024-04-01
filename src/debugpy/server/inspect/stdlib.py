# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

"""Object inspection for builtin Python types."""

from collections.abc import Iterable, Mapping
from itertools import count

from debugpy.common import log
from debugpy.server.inspect import ObjectInspector, IndexedChildObject


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


class IterableInspectorWithRepr(IterableInspector):
    def repr_prefix(self) -> str:
        return type(self.value).__name__ + "(("

    def repr_suffix(self) -> str:
        return "))"

    def repr_items(self) -> Iterable[object]:
        return self.value

    def iter_repr(self, context: ObjectInspector.ReprContext) -> Iterable[str]:
        yield self.repr_prefix()
        for i, item in enumerate(self.value):
            if i > 0:
                yield ", "
            yield from context.nest(item)
        yield self.repr_suffix()


class MappingInspectorWithRepr(MappingInspector):
    def repr_prefix(self) -> str:
        return type(self.value).__name__ + "({"

    def repr_suffix(self) -> str:
        return "})"

    def iter_repr(self, context: ObjectInspector.ReprContext) -> Iterable[str]:
        yield self.repr_prefix()
        for i, (key, value) in enumerate(self.value.items()):
            if i > 0:
                yield ", "
            yield from context.nest(key)
            yield ": "
            yield from context.nest(value)
        yield self.repr_suffix()


class StrLikeInspector(IterableInspector):
    value: str | bytes | bytearray

    def repr_prefix(self) -> str:
        return "'"

    def repr_suffix(self) -> str:
        return "'"

    def indexed_children(self) -> Iterable[IndexedChildObject]:
        if isinstance(self.value, str):
            # Indexing str yields str, which is not very useful for debugging.
            # What we want is to show the ordinal character values, similar
            # to how it works for bytes & bytearray.
            for i, ch in enumerate(self.value):
                yield IndexedChildObject(i, ord(ch))
        else:
            yield from super().indexed_children()

    def iter_repr(self, context: ObjectInspector.ReprContext) -> Iterable[str]:
        prefix = self.repr_prefix()
        suffix = self.repr_suffix()
        yield prefix
        i = 0
        while i < len(self.value):
            # Optimistically assume that no escaping will be needed.
            chunk_size = max(1, context.chars_remaining)
            chunk = repr(self.value[i : i + chunk_size])
            yield chunk[len(prefix) : -len(suffix)]
            i += chunk_size
        yield suffix


class IntInspector(ObjectInspector):
    value: int

    def iter_repr(self, context: ObjectInspector.ReprContext) -> Iterable[str]:
        fs = "{:#x}" if self.format.hex else "{}"
        yield fs.format(self.value)


class BytesInspector(StrLikeInspector):
    def repr_prefix(self) -> str:
        return "b'"


class ByteArrayInspector(StrLikeInspector):
    def repr_prefix(self) -> str:
        return "bytearray(b'"

    def repr_suffix(self) -> str:
        return "')"


class StrInspector(StrLikeInspector):
    def indexed_children(self) -> Iterable[IndexedChildObject]:
        # Indexing str yields str, which is not very useful for debugging. We want
        # to show the ordinal character values, similar to how it works for bytes.
        for i, ch in enumerate(self.value):
            yield IndexedChildObject(i, ord(ch))


class ListInspector(IterableInspectorWithRepr):
    def repr_prefix(self) -> str:
        return "["

    def repr_suffix(self) -> str:
        return "]"


class TupleInspector(IterableInspectorWithRepr):
    def repr_prefix(self) -> str:
        return "("

    def repr_suffix(self) -> str:
        return ",)" if len(self.value) == 1 else ")"


class SetInspector(IterableInspectorWithRepr):
    def repr_prefix(self) -> str:
        return "{"

    def repr_suffix(self) -> str:
        return "}"


class FrozenSetInspector(IterableInspectorWithRepr):
    def repr_prefix(self) -> str:
        return "frozenset({"

    def repr_suffix(self) -> str:
        return "})"


class ArrayInspector(IterableInspectorWithRepr):
    def repr_prefix(self) -> str:
        return f"array({self.value.typecode!r}, ("

    def repr_suffix(self) -> str:
        return "))"


class DequeInspector(IterableInspectorWithRepr):
    pass


class DictInspector(MappingInspectorWithRepr):
    def repr_prefix(self) -> str:
        return "{"

    def repr_suffix(self) -> str:
        return "}"
