# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

"""Object inspection for builtin Python types."""

from collections.abc import Iterable
from itertools import count

from debugpy.common import log
from debugpy.server.inspect import ObjectInspector, IndexedChildObject
from debugpy.server.safe_repr import SafeRepr


class SequenceInspector(ObjectInspector):
    def indexed_children(self) -> Iterable[IndexedChildObject]:
        yield from super().indexed_children()
        try:
            it = iter(self.obj)
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
    def indexed_children(self) -> Iterable[IndexedChildObject]:
        yield from super().indexed_children()
        try:
            keys = self.obj.keys()
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
                value = self.obj[key]
            except BaseException as exc:
                value = exc
            yield IndexedChildObject(key, value)


class ListInspector(SequenceInspector):
    def repr(self) -> Iterable[str]:
        # TODO: move logic from SafeRepr here
        yield SafeRepr()(self.obj)
