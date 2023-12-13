# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

"""
Object inspection: rendering values, enumerating children etc.
"""

from typing import Iterable


class ChildObject:
    name: str
    value: object

    def __init__(self, value: object):
        self.value = value

    @property
    def name(self) -> str:
        raise NotImplementedError

    def expr(self, obj: object) -> str:
        raise NotImplementedError
    

class ChildAttribute(ChildObject):
    name: str

    def __init__(self, name: str, value: object):
        super().__init__(value)
        self.name = name

    def expr(self, obj_expr: str) -> str:
        return f"({obj_expr}).{self.name}"


class ObjectInspector:
    """
    Inspects a generic object. Uses builtins.repr() to render values and dir() to enumerate children.
    """

    obj: object

    def __init__(self, obj: object):
        self.obj = obj

    def repr(self) -> Iterable[str]:
        yield repr(self.obj)
    
    def children(self) -> Iterable[ChildObject]:
        return sorted(self._attributes(), key=lambda var: var.name)

    def _attributes(self) -> Iterable[ChildObject]:
        # TODO: group class/instance/function/special
        try:
            names = dir(self.obj)
        except:
            names = []
        for name in names:
            if name.startswith("__"):
                continue
            try:
                value = getattr(self.obj, name)
            except BaseException as exc:
                value = exc
            try:
                if hasattr(type(value), "__call__"):
                    continue
            except:
                pass
            yield ChildAttribute(name, value)


def inspect(obj: object) -> ObjectInspector:
    from debugpy.server.inspect import stdlib

    # TODO: proper extensible registry
    match obj:
        case list():
            return stdlib.ListInspector(obj)
        case {}:
            return stdlib.MappingInspector(obj)
        case []:
            return stdlib.SequenceInspector(obj)
        case _:
            return ObjectInspector(obj)