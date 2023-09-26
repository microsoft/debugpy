# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import inspect
import sys
import threading
import traceback

from contextlib import contextmanager
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from sys import monitoring
from types import CodeType, FrameType
from typing import ClassVar, Dict, Iterable, List, Literal, Union

from debugpy.server import adapter
from debugpy.server.eval import Scope, VariableContainer

# Shared for all global state pertaining to breakpoints and stepping.
_cvar = threading.Condition()

# IDs of threads that are currently pausing or paused.
_pause_ids = set()

_steps = {}


@contextmanager
def cvar(who):
    #print(end=f"ACQUIRING {who}\n")
    with _cvar:
        #print(end=f"ACQUIRED {who}\n")
        yield
        #print(end=f"RELEASING {who}\n")
    #print(end=f"RELEASED {who}\n")


@dataclass
class Thread:
    id: int = field(init=False)
    thread: threading.Thread

    def __post_init__(self):
        # TODO: map 32-bit DAP thread IDs to (potentially) 64-bit Python thread IDs.
        # Otherwise, large thread IDs (common on Linux) will be truncated when they are serialized as JSON.
        self.id = self.thread.ident

    def __getstate__(self):
        return {
            "id": self.id,
            "name": self.thread.name,
        }

    @property
    def is_traced(self):
        return not getattr(self.thread, "pydev_do_not_trace", False)

    @property
    def name(self):
        return self.thread.name

    @classmethod
    def enumerate(self) -> List["Thread"]:
        return [
            thread
            for t in threading.enumerate()
            for thread in [Thread(t)]
            if thread.is_traced
        ]
    
    @classmethod
    def get(self, id: int) -> Union["Thread", None]:
        for thread in self.enumerate():
            if thread.id == id:
                return thread
        return None
    
    def stack_trace(self) -> Iterable["StackFrame"]:
        try:
            (fobj,) = (fobj for (id, fobj) in sys._current_frames().items() if id == self.id)
        except ValueError:
            raise ValueError(f"Can't get frames for inactive Thread({self.id})")
        for fobj, _ in traceback.walk_stack(fobj):
            frame = StackFrame.from_frame_object(self, fobj)
            if not frame.is_internal():
                yield frame
    

@dataclass
class StackFrame:
    thread: Thread
    frame_object: FrameType

    id: int = field(init=False)
    _path: Path = field(init=False)
    _scopes: List[Scope] = field(init=False, default=None)

    _last_id: ClassVar[int] = 0
    _all: ClassVar[Dict[int, "StackFrame"]] = {}

    def __post_init__(self):
        StackFrame._last_id += 1
        self.id = StackFrame._last_id
        self._path = None
        self._all[self.id] = self

    def __getstate__(self):
        return {
            "id": self.id,
            "name": self.frame_object.f_code.co_name,
            "source": {
                # TODO: use "sourceReference" when path isn't available (e.g. decompiled code)
                "path": str(self.path()),
            },
            "line": self.frame_object.f_lineno,
            "column": 1,  # TODO
            # TODO: "endLine", "endColumn", "moduleId", "instructionPointerReference"
        }

    @property
    def line(self) -> int:
        return self.frame_object.f_lineno

    def path(self) -> Path:
        if self._path is None:
            path = Path(self.frame_object.f_code.co_filename)
            try:
                path = path.resolve()
            except (OSError, RuntimeError):
                pass
            # No need to sync this.
            self._path = path
        return self._path

    def is_internal(self) -> bool:
        # TODO: filter internal frames properly
        parts = self.path().parts
        internals = ["debugpy", "threading"]
        return any(part.startswith(s) for s in internals for part in parts)
    
    @classmethod
    def get(self, id: int) -> "StackFrame":
        return self._all.get(id, None)

    @classmethod
    def from_frame_object(self, thread: Thread, frame_object: FrameType) -> "StackFrame":
        for frame in self._all.values():
            if frame.thread.id == thread.id and frame.frame_object is frame_object:
                return frame
        return StackFrame(thread, frame_object)
    
    def scopes(self) -> List[Scope]:
        if self._scopes is None:
            self._scopes = [
                Scope(self.frame_object, "local"),
                Scope(self.frame_object, "global"),
            ]
        return self._scopes
    
    @classmethod
    def invalidate(self, thread_id: int):
        frames = [frame for frame in self._all.values() if frame.thread.id == thread_id]
        VariableContainer.invalidate(*frames)


@dataclass
class Step:
    step: Literal["in", "out", "over"]
    origin: FrameType = None
    origin_line: int = None


@dataclass
class Breakpoint:
    path: Path
    line: int
    is_enabled: bool = True

    id: int = field(init=False)

    _last_id: ClassVar[int] = 0

    _all: ClassVar[Dict[int, "Breakpoint"]] = {}

    _at: ClassVar[Dict[Path, Dict[int, List["Breakpoint"]]]] = defaultdict(
        lambda: defaultdict(lambda: [])
    )

    def __post_init__(self):
        Breakpoint._last_id += 1
        self.id = Breakpoint._last_id
        with cvar(1):
            self._all[self.id] = self
            self._at[self.path][self.line].append(self)
            _cvar.notify_all()

    def __getstate__(self):
        return {
            "line": self.line,
            "verified": True,  # TODO
        }

    def is_hit(self, frame: StackFrame):
        with cvar(2):
            # Check path last since path resolution is potentially expensive.
            return (
                self.is_enabled
                and frame.line == self.line
                and frame.path() == self.path
            )

    @classmethod
    def at(self, path: str, line: int) -> List["Breakpoint"]:
        with cvar(3):
            return self._at[path][line]

    @classmethod
    def clear(self, paths: Iterable[str] = None):
        #print("clear-bp", paths)
        if paths is not None:
            paths = [Path(path).resolve() for path in paths]
        with cvar(4):
            if paths is None:
                paths = list(self._at.keys())
            for path in paths:
                bps_in = self._at.pop(path, {}).values()
                for bps_at in bps_in:
                    for bp in bps_at:
                        del self._all[bp.id]
            _cvar.notify_all()
        monitoring.restart_events()

    @classmethod
    def set(self, path: str, line: int) -> "Breakpoint":
        try:
            path = Path(path).resolve()
        except (OSError, RuntimeError):
            pass
        #print("set-bp", path, line)
        bp = Breakpoint(path, line)
        monitoring.restart_events()
        return bp

    def enable(self, is_enabled: bool):
        with cvar(5):
            self.is_enabled = is_enabled
            _cvar.notify_all()


def start():
    for thread in Thread.enumerate():
        adapter().channel.send_event(
            "thread",
            {
                "reason": "started",
                "threadId": thread.id,
                "name": thread.name,
            },
        )

    monitoring.use_tool_id(monitoring.DEBUGGER_ID, "debugpy")
    monitoring.set_events(
        monitoring.DEBUGGER_ID,
        (
            monitoring.events.LINE
            | monitoring.events.PY_START
            | monitoring.events.PY_RETURN
            | monitoring.events.PY_RESUME
            | monitoring.events.PY_YIELD
            | monitoring.events.PY_THROW
            | monitoring.events.PY_UNWIND
            | monitoring.events.RAISE
            | monitoring.events.RERAISE
            | monitoring.events.EXCEPTION_HANDLED
        ),
    )

    trace_funcs = {
        monitoring.events.LINE: _trace_line,
        monitoring.events.PY_START: _trace_py_start,
        monitoring.events.PY_RESUME: _trace_py_resume,
        monitoring.events.PY_RETURN: _trace_py_return,
        monitoring.events.PY_YIELD: _trace_py_yield,
        monitoring.events.PY_THROW: _trace_py_throw,
        monitoring.events.PY_UNWIND: _trace_py_unwind,
        monitoring.events.RAISE: _trace_raise,
        monitoring.events.RERAISE: _trace_reraise,
        monitoring.events.EXCEPTION_HANDLED: _trace_exception_handled,
    }
    for event, func in trace_funcs.items():
        monitoring.register_callback(monitoring.DEBUGGER_ID, event, func)


def pause(thread_ids: List[int] = None):
    #print(f"PAUSE {thread_ids=}")
    if thread_ids is None:
        thread_ids = [thread.id for thread in Thread.enumerate()]

    # TODO: handle race between the above and new threads starting when doing pause-the-world.
    with cvar(6):
        _pause_ids.update(thread_ids)
        _cvar.notify_all()
    monitoring.restart_events()


def resume(thread_ids: List[int] = None):
    #print(f"RESUME {thread_ids=}")
    with cvar(7):
        if thread_ids is None:
            _pause_ids.clear()
        else:
            _pause_ids.difference_update(thread_ids)
        _cvar.notify_all()
    monitoring.restart_events()


def abandon_step(thread_ids: List[int] = None):
    #print(f"ABANDON_STEP {thread_ids=}")
    with cvar(8):
        if thread_ids is None:
            thread_ids = [thread.id for thread in Thread.enumerate()]
        for thread_id in thread_ids:
            _steps.pop(thread_id, None)
        _cvar.notify_all()
    monitoring.restart_events()    


def step_in(thread_id: int):
    with cvar(9):
        _steps[thread_id] = Step("in")
        _pause_ids.clear()
        _cvar.notify_all()
    monitoring.restart_events()


def step_out(thread_id: int):
    with cvar(10):
        _steps[thread_id] = Step("out")
        _pause_ids.clear()
        _cvar.notify_all()
    monitoring.restart_events()


def step_over(thread_id: int):
    with cvar(11):
        _steps[thread_id] = Step("over")
        _pause_ids.clear()
        _cvar.notify_all()
    monitoring.restart_events()


# On shutdown, modules go away (become None), but _trace_line is still invoked.
DISABLE = monitoring.DISABLE


def _stop(frame_obj: FrameType, reason: str, hit_breakpoints: Iterable[Breakpoint] = ()):
    thread_id = threading.get_ident()
    #print(f"STOP {thread_id=}, {reason=}, {hit_breakpoints=}")
    with cvar(12):
        if thread_id not in _pause_ids:
            #print("STOP: not paused")
            return

        #print("SENDING...")
        adapter().channel.send_event(
            "stopped",
            {
                "reason": reason,
                "threadId": threading.get_ident(),
                "allThreadsStopped": False,  # TODO
                "hitBreakpointIds": [bp.id for bp in hit_breakpoints],
            },
        )
        #print("SENT!")

        #print(f"BLOCK {thread_id=}")
        while thread_id in _pause_ids:
            _cvar.wait()
        #print(f"UNBLOCK {thread_id=}")

        step = _steps.get(thread_id, None)
        if step is not None and step.origin is None:
            step.origin = frame_obj
            step.origin_line = frame_obj.f_lineno


def _trace_line(code: CodeType, line_number: int):
    if monitoring is None:
        return DISABLE
    
    thread = Thread(threading.current_thread())
    if not thread.is_traced:
        return DISABLE

    stop_reason = None
    with cvar(13):
        if thread.id in _pause_ids:
            stop_reason = "pause"

        step = _steps.get(thread.id, None)
        is_stepping = step is not None and step.origin is not None
        if is_stepping:
            # TODO: use CALL/RETURN/PY_RETURN to track these more efficiently.
            frame_obj = inspect.currentframe().f_back
            step_finished = False
            if step.step == "in":
                if frame_obj is not step.origin or line_number != step.origin_line:
                    step_finished = True
            elif step.step == "out":
                step_finished = True
                while frame_obj is not None:
                    if frame_obj is step.origin:
                        step_finished = False
                        break
                    frame_obj = frame_obj.f_back
            elif step.step == "over":
                step_finished = True
                while frame_obj is not None:
                    if frame_obj is step.origin and frame_obj.f_lineno == step.origin_line:
                        step_finished = False
                        break
                    frame_obj = frame_obj.f_back
            else:
                raise ValueError(f"Unknown step type: {step.step}")
            
            if step_finished:
                del _steps[thread.id]
                _pause_ids.add(thread.id)
                _cvar.notify_all()
                stop_reason = "step"

    if stop_reason is not None:
        return _stop(inspect.currentframe().f_back, stop_reason)

    path = Path(code.co_filename)
    try:
        path = path.resolve()
    except (OSError, RuntimeError):
        pass
    # print(f"TRACE_LINE {thread_id=}, {path=}, {line_number=}")

    bps = Breakpoint.at(path, line_number)
    if not bps and not is_stepping:
        return DISABLE

    frame = StackFrame(thread, inspect.currentframe().f_back)
    try:
        bps_hit = [bp for bp in bps if bp.is_hit(frame)]
        if bps_hit:
            #print("!BREAKPOINT HIT!")
            with cvar(14):
                _pause_ids.add(thread.id)
                _cvar.notify_all()
            return _stop(frame.frame_object, "breakpoint", bps_hit)
    finally:
        del frame


def _trace_py_start(code: CodeType, ip: int):
    if threading.current_thread() is not threading.main_thread():
        return
    #print(f"TRACE_PY_START {code=}, {ip=}")


def _trace_py_resume(code: CodeType, ip: int):
    if threading.current_thread() is not threading.main_thread():
        return
    #print(f"TRACE_PY_RESUME {code=}, {ip=}")


def _trace_py_return(code: CodeType, ip: int, retval: object):
    if threading.current_thread() is not threading.main_thread():
        return
    try:
        retval = repr(retval)
    except:
        retval = "<unrepresentable>"
    #print(f"TRACE_PY_RETURN {code=}, {ip=}, {retval=}")


def _trace_py_yield(code: CodeType, ip: int, retval: object):
    if threading.current_thread() is not threading.main_thread():
        return
    try:
        retval = repr(retval)
    except:
        retval = "<unrepresentable>"
    #print(f"TRACE_PY_YIELD {code=}, {ip=}, {retval=}")


def _trace_py_throw(code: CodeType, ip: int, exc: BaseException):
    if threading.current_thread() is not threading.main_thread():
        return
    try:
        exc = repr(exc)
    except:
        exc = "<unrepresentable>"
    #print(f"TRACE_PY_THROW {code=}, {ip=}, {exc=}")


def _trace_py_unwind(code: CodeType, ip: int, exc: BaseException):
    if threading.current_thread() is not threading.main_thread():
        return
    try:
        exc = repr(exc)
    except:
        exc = "<unrepresentable>"
    #print(f"TRACE_PY_UNWIND {code=}, {ip=}, {exc=}")


def _trace_raise(code: CodeType, ip: int, exc: BaseException):
    if threading.current_thread() is not threading.main_thread():
        return
    try:
        exc = repr(exc)
    except:
        exc = "<unrepresentable>"
    #print(f"TRACE_RAISE {code=}, {ip=}, {exc=}")


def _trace_reraise(code: CodeType, ip: int, exc: BaseException):
    if threading.current_thread() is not threading.main_thread():
        return
    try:
        exc = repr(exc)
    except:
        exc = "<unrepresentable>"
    #print(f"TRACE_RERAISE {code=}, {ip=}, {exc=}")


def _trace_exception_handled(code: CodeType, ip: int, exc: BaseException):
    if threading.current_thread() is not threading.main_thread():
        return
    try:
        exc = repr(exc)
    except:
        exc = "<unrepresentable>"
    #print(f"TRACE_EXCEPTION_HANDLED {code=}, {ip=}, {exc=}")
