# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import debugpy
import threading
from collections.abc import Iterable
from debugpy.server.inspect import inspect
from types import FrameType
from typing import ClassVar, Dict, Literal, Self

type ScopeKind = Literal["global", "nonlocal", "local"]
type StackFrame = "debugpy.server.tracing.StackFrame"


_lock = threading.RLock()


class VariableContainer:
    frame: StackFrame
    id: int

    _last_id: ClassVar[int] = 0
    _all: ClassVar[Dict[int, "VariableContainer"]] = {}

    def __init__(self, frame: StackFrame):
        self.frame = frame
        with _lock:
            VariableContainer._last_id += 1
            self.id = VariableContainer._last_id
            self._all[self.id] = self

    def __getstate__(self):
        return {"variablesReference": self.id}

    def __repr__(self):
        return f"{type(self).__name__}{self.__getstate__()}"

    @classmethod
    def get(cls, id: int) -> Self | None:
        with _lock:
            return cls._all.get(id)

    def variables(self) -> Iterable["Variable"]:
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


class Scope(VariableContainer):
    frame: FrameType
    kind: ScopeKind

    def __init__(self, frame: StackFrame, kind: ScopeKind):
        super().__init__(frame)
        self.kind = kind

    def __getstate__(self):
        state = super().__getstate__()
        state.update(
            {
                "name": self.kind,
                "presentationHint": self.kind,
            }
        )
        return state

    def variables(self) -> Iterable["Variable"]:
        match self.kind:
            case "global":
                d = self.frame.f_globals
            case "local":
                d = self.frame.f_locals
            case _:
                raise ValueError(f"Unknown scope kind: {self.kind}")
        for name, value in d.items():
            yield Variable(self.frame, name, value)


class Variable(VariableContainer):
    name: str
    value: object
    # TODO: evaluateName, memoryReference, presentationHint

    def __init__(self, frame: StackFrame, name: str, value: object):
        super().__init__(frame)
        self.name = name
        self.value = value

    def __getstate__(self):
        state = super().__getstate__()
        state.update(
            {
                "name": self.name,
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

    def variables(self) -> Iterable["Variable"]:
        for child in inspect(self.value).children():
            yield Variable(self.frame, child.name, child.value)


def evaluate(expr: str, frame_id: int) -> Variable:
    from debugpy.server.tracing import StackFrame

    frame = StackFrame.get(frame_id)
    if frame is None:
        raise ValueError(f"Invalid frame ID: {frame_id}")
    fobj = frame.frame_object
    try:
        code = compile(expr, "<string>", "eval")
        result = eval(code, fobj.f_globals, fobj.f_locals)
    except BaseException as exc:
        result = exc
    return Variable(frame, expr, result)
