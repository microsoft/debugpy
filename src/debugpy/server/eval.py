# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import ctypes
import itertools
import debugpy
import threading
from collections.abc import Iterable, Set 
from debugpy.common import log
from debugpy.server.inspect import inspect
from typing import ClassVar, Literal, Optional, Self

type StackFrame = "debugpy.server.tracing.StackFrame"
type VariableFilter = Set[Literal["named", "indexed"]]


_lock = threading.RLock()


class VariableContainer:
    frame: StackFrame
    id: int

    _last_id: ClassVar[int] = 0
    _all: ClassVar[dict[int, "VariableContainer"]] = {}

    def __init__(self, frame: StackFrame):
        self.frame = frame
        with _lock:
            VariableContainer._last_id += 1
            self.id = VariableContainer._last_id
            self._all[self.id] = self

    def __getstate__(self) -> dict[str, object]:
        return {"variablesReference": self.id}

    def __repr__(self):
        return f"{type(self).__name__}({self.id})"

    @classmethod
    def get(cls, id: int) -> Self | None:
        with _lock:
            return cls._all.get(id)

    def variables(
        self, filter: VariableFilter, start: int = 0, count: Optional[int] = None
    ) -> Iterable["Variable"]:
        raise NotImplementedError

    def set_variable(self, name: str, value: str) -> "Value":
        raise NotImplementedError

    @classmethod
    def invalidate(self, *frames: Iterable[StackFrame]) -> None:
        with _lock:
            ids = [
                id
                for id, var in self._all.items()
                if any(frame is var.frame for frame in frames)
            ]
            for id in ids:
                del self._all[id]


class Value(VariableContainer):
    value: object
    # TODO: memoryReference, presentationHint

    def __init__(self, frame: StackFrame, value: object):
        super().__init__(frame)
        self.value = value

    def __getstate__(self) -> dict[str, object]:
        state = super().__getstate__()
        state.update(
            {
                "value": self.repr,
                "type": self.typename,
            }
        )
        return state

    @property
    def typename(self) -> str:
        try:
            return type(self.value).__name__
        except:
            return ""

    @property
    def repr(self) -> str:
        return "".join(inspect(self.value).repr())

    def variables(
        self, filter: VariableFilter, start: int = 0, count: Optional[int] = None
    ) -> Iterable["Variable"]:
        children = inspect(self.value).children(
            include_attrs=("named" in filter),
            include_items=("indexed" in filter),
        )
        stop = None if count is None else start + count
        log.info("Computing {0} children of {1!r} in range({2}, {3}).", filter, self, start, stop)
        children = itertools.islice(children, start, stop)
        for child in children:
            yield Variable(self.frame, child.name, child.value)

    def set_variable(self, name: str, value_expr: str) -> "Value":
        value = self.frame.evaluate(value_expr)
        if name.startswith("[") and name.endswith("]"):
            key_expr = name[1:-1]
            key = self.frame.evaluate(key_expr)
            self.value[key] = value
            result = self.value[key]
        else:
            setattr(self.value, name, value)
            result = getattr(self.value, name)
        return Value(self.frame, result)


class Result(Value):
    def __getstate__(self) -> dict[str, object]:
        state = super().__getstate__()
        state["result"] = state.pop("value")
        return state


class Variable(Value):
    name: str
    # TODO: evaluateName

    def __init__(self, frame: StackFrame, name: str, value: object):
        super().__init__(frame, value)
        self.name = name

    def __getstate__(self) -> dict[str, object]:
        state = super().__getstate__()
        state["name"] = self.name
        return state


class Scope(Variable):
    def __init__(self, frame: StackFrame, name: str, storage: dict[str, object]):
        class ScopeObject:
            def __dir__(self):
                return list(storage.keys())

            def __getattr__(self, name):
                return storage[name]

            def __setattr__(self, name, value):
                storage[name] = value
                # Until PEP 667 is implemented, this is necessary to propagate the changes
                # from the dict to actual locals.
                try:
                    PyFrame_LocalsToFast = ctypes.pythonapi.PyFrame_LocalsToFast
                except:
                    pass
                else:
                    PyFrame_LocalsToFast(
                        ctypes.py_object(frame.python_frame), ctypes.c_int(0)
                    )

        super().__init__(frame, name, ScopeObject())
