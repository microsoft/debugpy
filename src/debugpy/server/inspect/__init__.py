# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

"""
Object inspection: rendering values, enumerating children etc.
"""

from collections.abc import Iterable


class ChildObject:
    key: str
    value: object

    def __init__(self, value: object):
        self.value = value

    def expr(self, parent_expr: str) -> str:
        raise NotImplementedError


class NamedChildObject(ChildObject):
    def __init__(self, name: str, value: object):
        super().__init__(value)
        self.key = name

    @property
    def name(self) -> str:
        return self.key

    def expr(self, parent_expr: str) -> str:
        return f"({parent_expr}).{self.name}"


class LenChildObject(NamedChildObject):
    def __init__(self, parent: object):
        super().__init__("len()", len(parent))

    def expr(self, parent_expr: str) -> str:
        return f"len({parent_expr})"


class IndexedChildObject(ChildObject):
    key_object: object
    indexer: str

    def __init__(self, key: object, value: object):
        super().__init__(value)
        self.key_object = key
        self.indexer = None

    @property
    def key(self) -> str:
        if self.indexer is None:
            key_repr = "".join(inspect(self.key_object).repr())
            self.indexer = f"[{key_repr}]"
        return self.indexer

    def expr(self, parent_expr: str) -> str:
        return f"({parent_expr}){self.key}"


class ObjectInspector:
    """
    Inspects a generic object. Uses builtins.repr() to render values and dir() to enumerate children.
    """

    obj: object

    def __init__(self, obj: object):
        self.obj = obj

    def repr(self) -> Iterable[str]:
        try:
            result = repr(self.obj)
        except BaseException as exc:
            try:
                result = f"<repr() error: {exc}>"
            except:
                result = "<repr() error>"
        yield result

    def children(self) -> Iterable[ChildObject]:
        yield from self.named_children()
        yield from self.indexed_children()

    def indexed_children_count(self) -> int:
        try:
            return len(self.obj)
        except:
            return 0

    def indexed_children(self) -> Iterable[IndexedChildObject]:
        return ()

    def named_children_count(self) -> int:
        return len(tuple(self.named_children()))

    def named_children(self) -> Iterable[NamedChildObject]:
        def attrs():
            try:
                names = dir(self.obj)
            except:
                names = ()

            # TODO: group class/instance/function/special
            for name in names:
                if name.startswith("__"):
                    continue
                try:
                    value = getattr(self.obj, name)
                except BaseException as exc:
                    value = exc
                try:
                    if hasattr(value, "__call__"):
                        continue
                except:
                    pass
                yield NamedChildObject(name, value)

            try:
                yield LenChildObject(self.obj)
            except:
                pass

        return sorted(attrs(), key=lambda var: var.name)


def inspect(obj: object) -> ObjectInspector:
    from debugpy.server.inspect import stdlib

    # TODO: proper extensible registry
    match obj:
        case list():
            return stdlib.ListInspector(obj)
        case {}:
            return stdlib.MappingInspector(obj)
        case [*_] | set() | frozenset() | str() | bytes() | bytearray():
            return stdlib.SequenceInspector(obj)
        case _:
            return ObjectInspector(obj)
