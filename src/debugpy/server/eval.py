# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import threading

from collections.abc import Iterable, Mapping
from itertools import count
from types import FrameType
from typing import ClassVar, Dict, Literal, Self

from debugpy.server import tracing
from debugpy.common import log
from debugpy.server.safe_repr import SafeRepr

ScopeKind = Literal["global", "nonlocal", "local"]


_lock = threading.RLock()


class VariableContainer:
    frame: "tracing.StackFrame"
    id: int

    _last_id: ClassVar[int] = 0
    _all: ClassVar[Dict[int, "VariableContainer"]] = {}

    def __init__(self, frame: "tracing.StackFrame"):
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
    def invalidate(self, *frames: Iterable["tracing.StackFrame"]) -> None:
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

    def __init__(self, frame: "tracing.StackFrame", kind: ScopeKind):
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

    def __init__(self, frame: "tracing.StackFrame", name: str, value: object):
        super().__init__(frame)
        self.name = name
        self.value = value

        if isinstance(value, Mapping):
            self._items = self._items_dict
        else:
            try:
                it = iter(value)
            except:
                it = None
            # Use (iter(value) is value) to distinguish iterables from iterators.
            if it is not None and it is not value:
                self._items = self._items_iterable

    @property
    def typename(self) -> str:
        try:
            return type(self.value).__name__
        except:
            return ""

    @property
    def repr(self) -> str:
        return SafeRepr()(self.value)

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

    def variables(self) -> Iterable["Variable"]:
        get_name = lambda var: var.name
        return [
            *sorted(self._attributes(), key=get_name),
            *sorted(self._synthetic(), key=get_name),
            *self._items(),
        ]

    def _attributes(self) -> Iterable["Variable"]:
        # TODO: group class/instance/function/special
        try:
            names = dir(self.value)
        except:
            names = []
        for name in names:
            if name.startswith("__"):
                continue
            try:
                value = getattr(self.value, name)
            except BaseException as exc:
                value = exc
            try:
                if hasattr(type(value), "__call__"):
                    continue
            except:
                pass
            yield Variable(self.frame, name, value)

    def _synthetic(self) -> Iterable["Variable"]:
        try:
            length = len(self.value)
        except:
            pass
        else:
            yield Variable(self.frame, "len()", length)

    def _items(self) -> Iterable["Variable"]:
        return ()

    def _items_iterable(self) -> Iterable["Variable"]:
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
            yield Variable(self.frame, f"[{i}]", item)

    def _items_dict(self) -> Iterable["Variable"]:
        try:
            keys = self.value.keys()
        except:
            return
        it = iter(keys)
        safe_repr = SafeRepr()
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
            yield Variable(self.frame, f"[{safe_repr(key)}]", value)


def evaluate(expr: str, frame_id: int):
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
