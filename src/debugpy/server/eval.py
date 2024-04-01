# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

"""
DAP entities related to expression evaluation and inspection of variables and scopes.

Classes here are mostly wrappers around the actual object inspection logic implemented
in debugpy.server.inspect which adapts it to DAP, allowing debugpy.server.inspect to be
unit-tested in isolation.
"""

import ctypes
import itertools
import debugpy
import threading
from collections.abc import Iterable, Set
from debugpy.common import log
from debugpy.server.inspect import ObjectInspector, ValueFormat, inspect
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
        self,
        filter: VariableFilter,
        format: ValueFormat,
        start: int = 0,
        count: Optional[int] = None,
    ) -> Iterable["Variable"]:
        raise NotImplementedError

    def set_variable(self, name: str, value: str, format: ValueFormat) -> "Value":
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
    format: ValueFormat
    # TODO: memoryReference, presentationHint

    def __init__(self, frame: StackFrame, value: object, format: ValueFormat):
        super().__init__(frame)
        self.value = value
        self.format = format

    def __getstate__(self) -> dict[str, object]:
        state = super().__getstate__()
        state.update(
            {
                "type": self.typename,
                "value": self.repr(),
                "namedVariables": self.inspector.named_children_count(),
                "indexedVariables": self.inspector.indexed_children_count(),
            }
        )
        return state

    @property
    def inspector(self) -> ObjectInspector:
        return inspect(self.value, self.format)

    @property
    def typename(self) -> str:
        try:
            return type(self.value).__name__
        except:
            return ""

    def repr(self) -> str:
        return self.inspector.repr()

    def variables(
        self,
        filter: VariableFilter,
        format: ValueFormat,
        start: int = 0,
        count: Optional[int] = None,
    ) -> Iterable["Variable"]:
        stop = None if count is None else start + count
        log.info(
            "Computing {0} children of {1!r} in range({2}, {3}).",
            filter,
            self,
            start,
            stop,
        )

        inspector = inspect(self.value, format)
        children = itertools.chain(
            inspector.named_children() if "named" in filter else (),
            inspector.indexed_children() if "indexed" in filter else (),
        )
        children = itertools.islice(children, start, stop)
        for child in children:
            yield Variable(self.frame, child.accessor(format), child.value, format)

    def set_variable(self, name: str, value_expr: str, format: ValueFormat) -> "Value":
        value = self.frame.evaluate(value_expr)
        if name.startswith("[") and name.endswith("]"):
            key_expr = name[1:-1]
            key = self.frame.evaluate(key_expr)
            self.value[key] = value
            result = self.value[key]
        else:
            setattr(self.value, name, value)
            result = getattr(self.value, name)
        return Value(self.frame, result, format)


class Result(Value):
    def __getstate__(self) -> dict[str, object]:
        state = super().__getstate__()
        state["result"] = state.pop("value")
        return state


class Variable(Value):
    name: str
    # TODO: evaluateName

    def __init__(self, frame: StackFrame, name: str, value: object, format: ValueFormat):
        super().__init__(frame, value, format)
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

        super().__init__(frame, name, ScopeObject(), ValueFormat())
