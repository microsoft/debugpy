# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import re
import sys
import threading
import traceback
from collections import defaultdict
from dataclasses import dataclass
from debugpy import server
from debugpy.common import log
from debugpy.server.eval import Scope, VariableContainer
from pathlib import Path
from sys import monitoring
from types import CodeType, FrameType
from typing import Callable, ClassVar, Dict, Iterable, List, Literal, Union

# Shared for all global state pertaining to breakpoints and stepping.
_cvar = threading.Condition()


class Thread:
    """
    Represents a DAP Thread object. Instances must never be created directly;
    use Thread.from_python_thread() instead.
    """

    id: int
    """DAP ID of this thread. Distinct from thread.ident."""

    python_thread: threading.Thread
    """The Python thread object this DAP Thread represents."""

    is_known_to_adapter: bool
    """
    Whether this thread has been reported to the adapter via the
    DAP "thread" event with "reason":"started".
    """

    _last_id = 0
    _all: ClassVar[Dict[int, "Thread"]] = {}

    def __init__(self, python_thread):
        """
        Create a new Thread object for the given thread. Do not invoke directly;
        use Thread.get() instead.
        """
        self.python_thread = python_thread
        self.is_known_to_adapter = False

        with _cvar:
            # Thread IDs are serialized as JSON numbers in DAP, which are handled as 64-bit
            # floats by most DAP clients. However, OS thread IDs can be large 64-bit integers
            # on some platforms. To avoid loss of precision, we map all thread IDs to 32-bit
            # signed integers; if the original ID fits, we use it as is, otherwise we use a
            # generated negative ID that is guaranteed to fit.
            self.id = self.python_thread.ident
            if self.id != float(self.id):
                Thread._last_id -= 1
                self.id = Thread._last_id
            self._all[self.id] = self

        log.info(
            f"DAP Thread(id={self.id}) created for Python Thread(ident={self.python_thread.ident})"
        )

    def __getstate__(self):
        return {
            "id": self.id,
            "name": self.name,
        }

    @property
    def is_debugpy_thread(self):
        return getattr(self.python_thread, "is_debugpy_thread", False)

    @property
    def is_traced(self):
        return not self.is_debugpy_thread

    @property
    def name(self):
        return self.python_thread.name

    @classmethod
    def from_python_thread(self, python_thread: threading.Thread = None) -> "Thread":
        """
        Returns the DAP Thread object corresponding to the given Python thread, or for
        the current Python thread if None, creating it and reporting it to adapter if
        necessary.
        """
        if python_thread is None:
            python_thread = threading.current_thread()
        with _cvar:
            for thread in self._all.values():
                if thread.python_thread is python_thread:
                    break
            else:
                thread = Thread(python_thread)
        thread.make_known_to_adapter()
        return thread

    @classmethod
    def get(self, id: int) -> Union["Thread", None]:
        """
        Finds a thread by its DAP ID. Returns None if ID is unknown.
        """
        with _cvar:
            return self._all.get(id, None)

    @classmethod
    def enumerate(self) -> List["Thread"]:
        """
        Returns a list of all running threads in this process.
        """
        return [
            thread
            for python_thread in threading.enumerate()
            for thread in [Thread.from_python_thread(python_thread)]
            if thread.is_traced
        ]

    def make_known_to_adapter(self):
        """
        If adapter is connected to this process, reports this thread to it via DAP
        "thread" event with "reason":"started" if it hasn't been reported already.
        Returns True if thread is now known to the adapter, and False if there was
        no adapter to report it to.
        """
        with _cvar:
            if not self.is_traced:
                return False
            if self.is_known_to_adapter:
                return True
            adapter = server.adapter()
            if adapter is None:
                return False
            adapter.channel.send_event(
                "thread",
                {
                    "reason": "started",
                    "threadId": self.id,
                    "name": self.name,
                },
            )
            self.is_known_to_adapter = True
            return True

    def stack_trace(self) -> Iterable["StackFrame"]:
        """
        Returns an iterable of StackFrame objects for the current stack of this thread,
        starting with the topmost frame.
        """
        try:
            (fobj,) = (
                fobj for (id, fobj) in sys._current_frames().items() if id == self.id
            )
        except ValueError:
            raise ValueError(f"Can't get frames for inactive Thread({self.id})")
        for fobj, _ in traceback.walk_stack(fobj):
            frame = StackFrame.from_frame_object(self, fobj)
            if not frame.is_internal():
                yield frame


class StackFrame:
    """
    Represents a DAP StackFrame object. Instances must never be created directly;
    use StackFrame.from_frame_object() instead.
    """

    thread: Thread
    frame_object: FrameType

    id: int
    _path: Path
    _scopes: List[Scope]

    _last_id = 0
    _all: ClassVar[Dict[int, "StackFrame"]] = {}

    def __init__(self, thread: Thread, frame_object: FrameType):
        """
        Create a new StackFrame object for the given thread and frame object. Do not
        invoke directly; use StackFrame.from_frame_object() instead.
        """
        StackFrame._last_id += 1
        self.id = StackFrame._last_id
        self.thread = thread
        self.frame_object = frame_object
        self._path = None
        self._scopes = None
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
            # No need to sync this since all instances are equivalent.
            self._path = path
        return self._path

    def is_internal(self) -> bool:
        # TODO: filter internal frames properly
        parts = self.path().parts
        internals = ["debugpy", "threading"]
        return any(part.startswith(s) for s in internals for part in parts)

    @classmethod
    def from_frame_object(
        self, thread: Thread, frame_object: FrameType
    ) -> "StackFrame":
        for frame in self._all.values():
            if frame.thread is thread and frame.frame_object is frame_object:
                return frame
        return StackFrame(thread, frame_object)

    @classmethod
    def get(self, id: int) -> "StackFrame":
        return self._all.get(id, None)

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


class Condition:
    """
    Expression that must be true for the breakpoint to be triggered.
    """

    expression: str
    """Python expression that must evaluate to True for the breakpoint to be triggered."""

    _code: CodeType

    def __init__(self, breakpoint: "Breakpoint", expression: str):
        self.expression = expression
        self._code = compile(
            expression, f"breakpoint-{breakpoint.id}-condition", "eval"
        )

    def test(self, frame: StackFrame) -> bool:
        """
        Returns True if the breakpoint should be triggered in the specified frame.
        """
        try:
            return bool(
                eval(
                    self._code,
                    frame.frame_object.f_globals,
                    frame.frame_object.f_locals,
                )
            )
        except:
            log.exception(
                f"Exception while evaluating breakpoint condition: {self.expression}"
            )
            return False


class HitCondition:
    """
    Hit count expression that must be True for the breakpoint to be triggered.

    Must have the format `[<operator>]<count>`, where <count> is a positive integer literal,
    and <operator> is one of `==` `>` `>=` `<` `<=` `%`, defaulting to `==` if unspecified.

    Examples:
        5: break on the 5th hit
        ==5: ditto
        >5: break on every hit after the 5th
        >=5: break on the 5th hit and thereafter
        %5: break on every 5th hit
    """

    _OPERATORS = {
        "==": lambda expected_count, count: count == expected_count,
        ">": lambda expected_count, count: count > expected_count,
        ">=": lambda expected_count, count: count >= expected_count,
        "<": lambda expected_count, count: count < expected_count,
        "<=": lambda expected_count, count: count <= expected_count,
        "%": lambda expected_count, count: count % expected_count == 0,
    }

    hit_condition: str
    _count: int
    _operator: Callable[[int, int], bool]

    def __init__(self, hit_condition: str):
        self.hit_condition = hit_condition
        m = re.match(r"([<>=]+)?(\d+)", hit_condition)
        if not m:
            raise ValueError(f"Invalid hit condition: {hit_condition}")
        self._count = int(m.group(2))
        try:
            op = self._OPERATORS[m.group(1) or "=="]
        except KeyError:
            raise ValueError(f"Invalid hit condition operator: {op}")
        self.test = lambda count: op(self._count, count)

    def test(self, count: int) -> bool:
        """
        Returns True if the breakpoint should be triggered on the given hit count.
        """
        # __init__ replaces this method with an actual implementation from _OPERATORS
        # when it parses the condition.
        raise NotImplementedError


class LogMessage:
    """
    A message with spliced expressions, to be logged when a breakpoint is triggered.
    """

    message: str
    """The message to be logged. May contain expressions in curly braces."""

    _code: CodeType
    """Compiled code object for the f-string corresponding to the message."""

    def __init__(self, breakpoint: "Breakpoint", message: str):
        self.message = message
        f_string = "f" + repr(message)
        self._code = compile(f_string, f"breakpoint-{breakpoint.id}-logMessage", "eval")

    def format(self, frame: StackFrame) -> str:
        """
        Formats the message using the specified frame's locals and globals.
        """
        try:
            return eval(
                self._code, frame.frame_object.f_globals, frame.frame_object.f_locals
            )
        except:
            log.exception(
                f"Exception while formatting breakpoint log message: {self.message}"
            )
            return self.message


class Breakpoint:
    """
    Represents a DAP Breakpoint.
    """

    id: int
    path: Path
    line: int
    is_enabled: bool

    condition: Condition | None

    hit_condition: HitCondition | None

    log_message: LogMessage | None

    hit_count: int
    """Number of times this breakpoint has been hit."""

    _last_id = 0

    _all: ClassVar[Dict[int, "Breakpoint"]] = {}

    _at: ClassVar[Dict[Path, Dict[int, List["Breakpoint"]]]] = defaultdict(
        lambda: defaultdict(lambda: [])
    )

    def __init__(
        self, path, line, *, condition=None, hit_condition=None, log_message=None
    ):
        with _cvar:
            Breakpoint._last_id += 1
            self.id = Breakpoint._last_id

        self.path = path
        self.line = line
        self.is_enabled = True
        self.condition = Condition(self, condition) if condition else None
        self.hit_condition = HitCondition(hit_condition) if hit_condition else None
        self.log_message = LogMessage(self, log_message) if log_message else None
        self.hit_count = 0

        with _cvar:
            self._all[self.id] = self
            self._at[self.path][self.line].append(self)
            _cvar.notify_all()

    def __getstate__(self):
        return {
            "line": self.line,
            "verified": True,  # TODO
        }

    @classmethod
    def at(self, path: str, line: int) -> List["Breakpoint"]:
        """
        Returns a list of all breakpoints at the specified location.
        """
        with _cvar:
            return self._at[path][line]

    @classmethod
    def clear(self, paths: Iterable[str] = None):
        """
        Removes all breakpoints in the specified files, or all files if None.
        """
        if paths is not None:
            paths = [Path(path).resolve() for path in paths]
        with _cvar:
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
    def set(
        self,
        path: str,
        line: int,
        *,
        condition=None,
        hit_condition=None,
        log_message=None,
    ) -> "Breakpoint":
        """
        Creates a new breakpoint at the specified location.
        """
        try:
            path = Path(path).resolve()
        except (OSError, RuntimeError):
            pass
        bp = Breakpoint(
            path,
            line,
            condition=condition,
            hit_condition=hit_condition,
            log_message=log_message,
        )
        monitoring.restart_events()
        return bp

    def enable(self, is_enabled: bool):
        """
        Enables or disables this breakpoint.
        """
        with _cvar:
            self.is_enabled = is_enabled
            _cvar.notify_all()

    def is_triggered(self, frame: StackFrame) -> bool | str:
        """
        Determines whether this breakpoint is triggered by the current line in the
        specified stack frame, and updates its hit count.

        If the breakpoint is triggered, returns a truthy value; if the breakpoint has
        a log message, it is formatted and returned, otherwise True is returned.
        """
        with _cvar:
            # Check path last since path resolution is potentially expensive.
            if (
                not self.is_enabled
                or frame.line != self.line
                or frame.path() != self.path
            ):
                return False

            # Hit count must be updated even if conditions are false and execution
            # isn't stopped.
            self.hit_count += 1

            # Check hit_condition first since it is faster than checking condition.
            if self.hit_condition is not None and not self.hit_condition.test(
                self.hit_count
            ):
                return False
            if self.condition is not None and not self.condition.test(frame):
                return False
            
            # If this is a logpoint, return the formatted message instead of True.
            if self.log_message is not None:
                return self.log_message.format(frame)

            return True


# sys.monitoring callbacks are defined in a separate submodule to enable tighter
# control over their use of global state; see comment there for details.
from .tracer import Tracer  # noqa
