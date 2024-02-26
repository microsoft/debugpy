# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import re
import threading
import traceback
from collections import defaultdict
from dataclasses import dataclass
from debugpy import server
from debugpy.common import log
from debugpy.server import new_dap_id
from debugpy.server.eval import Scope, VariableContainer
from pathlib import Path
from sys import monitoring
from types import CodeType, FrameType
from typing import Callable, ClassVar, Dict, Iterable, List, Literal, Union

# Shared for all global state pertaining to breakpoints and stepping.
_cvar = threading.Condition()


class Source:
    """
    Represents a DAP Source object.
    """

    path: str
    """
    Path to the source file; immutable. Note that this needs not be an actual valid
    path on the filesystem; values such as <string> or <stdin> are also allowed.
    """

    # TODO: support "sourceReference" for cases where path isn't available (e.g. decompiled code)

    def __init__(self, path: str):
        # If it is a valid file path, we want to resolve and normalize it, so that it
        # can be unambiguously compared to code object paths later.
        try:
            path = str(Path(path).resolve())
        except (OSError, RuntimeError):
            # Something like <string> or <stdin>
            pass
        self.path = path

    def __getstate__(self) -> dict:
        return {"path": self.path}

    def __repr__(self) -> str:
        return f"Source({self.path!r})"

    def __str__(self) -> str:
        return self.path

    def __eq__(self, other) -> bool:
        if not isinstance(other, Source):
            return False
        return self.path == other.path

    def __hash__(self) -> int:
        return hash(self.path)


class Thread:
    """
    Represents a DAP Thread object. Instances must never be created directly;
    use Thread.from_python_thread() instead.
    """

    id: int
    """DAP ID of this thread. Distinct from thread.ident."""

    python_thread: threading.Thread
    """The Python thread object this DAP Thread represents."""

    python_frame: FrameType | None
    """
    The Python frame object corresponding to the topmost stack frame on this thread
    if it is suspended, or None if it is running.
    """

    is_known_to_adapter: bool
    """
    Whether this thread has been reported to the adapter via the
    DAP "thread" event with "reason":"started".
    """

    is_traced: bool
    """
    Whether this thread is traced. Threads are normally traced, but API clients
    can exclude a specific thread from tracing.
    """

    _all: ClassVar[Dict[int, "Thread"]] = {}

    def __init__(self, python_thread: threading.Thread):
        """
        Create a new Thread object for the given thread. Do not invoke directly;
        use Thread.get() instead.
        """

        self.python_thread = python_thread
        self.current_frame = None
        self.is_known_to_adapter = False
        self.is_traced = True

        # Thread IDs are serialized as JSON numbers in DAP, which are handled as 64-bit
        # floats by most DAP clients. However, OS thread IDs can be large 64-bit integers
        # on some platforms. To avoid loss of precision, we map all thread IDs to 32-bit
        # signed integers; if the original ID fits, we use it as is, otherwise we use a
        # generated negative ID that is guaranteed to fit.
        self.id = self.python_thread.ident
        assert self.id is not None

        if self.id < 0 or self.id != float(self.id):
            self.id = new_dap_id()
        self._all[self.id] = self

        log.info(
            f"DAP {self} created for Python Thread(ident={self.python_thread.ident})"
        )

    def __repr__(self) -> str:
        return f"Thread({self.id})"

    def __getstate__(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
        }

    @property
    def name(self) -> str:
        return self.python_thread.name

    @classmethod
    def from_python_thread(self, python_thread: threading.Thread = None) -> "Thread":
        """
        Returns the DAP Thread object corresponding to the given Python thread, or for
        the current Python thread if None, creating it and reporting it to adapter if
        necessary. If the current thread is internal debugpy thread, returns None.
        """
        if python_thread is None:
            python_thread = threading.current_thread()
        if python_thread.ident is None:
            return None
        if getattr(python_thread, "is_debugpy_thread", False):
            return None
        with _cvar:
            for thread in self._all.values():
                if thread.python_thread.ident == python_thread.ident:
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
    def enumerate(self) -> list["Thread"]:
        """
        Returns all running threads in this process.
        """
        return [thread for thread in self._all.values() if thread.is_traced]

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
            with _cvar:
                python_frame = self.python_frame
        except ValueError:
            raise ValueError(f"Can't get frames for inactive Thread({self.id})")
        for python_frame, _ in traceback.walk_stack(python_frame):
            frame = StackFrame.from_frame_object(self, python_frame)
            log.info("{0}", f"{self}: {frame}")
            if not frame.is_internal():
                yield frame
        log.info("{0}", f"{self}: End stack trace.")


class StackFrame:
    """
    Represents a DAP StackFrame object. Instances must never be created directly;
    use StackFrame.from_frame_object() instead.
    """

    thread: Thread
    frame_object: FrameType

    id: int
    _source: Source | None
    _scopes: List[Scope]

    _all: ClassVar[Dict[int, "StackFrame"]] = {}

    def __init__(self, thread: Thread, frame_object: FrameType):
        """
        Create a new StackFrame object for the given thread and frame object. Do not
        invoke directly; use StackFrame.from_frame_object() instead.
        """
        self.id = new_dap_id()
        self.thread = thread
        self.frame_object = frame_object
        self._source = None
        self._scopes = None
        self._all[self.id] = self

    def __getstate__(self) -> dict:
        return {
            "id": self.id,
            "name": self.frame_object.f_code.co_name,
            "source": self.source(),
            "line": self.frame_object.f_lineno,
            "column": 1,  # TODO
            # TODO: "endLine", "endColumn", "moduleId", "instructionPointerReference"
        }

    def __repr__(self) -> str:
        result = f"StackFrame({self.id}, {self.frame_object}"
        if self.is_internal():
            result += ", internal=True"
        result += ")"
        return result

    @property
    def line(self) -> int:
        return self.frame_object.f_lineno

    def source(self) -> Source:
        if self._source is None:
            # No need to sync this since all instances created from the same path
            # are equivalent for all purposes.
            self._source = Source(self.frame_object.f_code.co_filename)
        return self._source

    def is_internal(self) -> bool:
        # TODO: filter internal frames properly
        parts = Path(self.source().path).parts
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

    def __repr__(self):
        return f"Step({self.step})"

    def is_complete(self, python_frame: FrameType) -> bool:
        is_complete = False
        if self.step == "in":
            is_complete = (
                python_frame is not self.origin
                or python_frame.f_lineno != self.origin_line
            )
        elif self.step == "over":
            is_complete = True
            for python_frame, _ in traceback.walk_stack(python_frame):
                if (
                    python_frame is self.origin
                    and python_frame.f_lineno == self.origin_line
                ):
                    is_complete = False
                    break
            return is_complete
        elif self.step == "out":
            while python_frame is not None:
                if python_frame is self.origin:
                    is_complete = False
                    break
        else:
            raise ValueError(f"Unknown step type: {self.step}")
        return is_complete


class Condition:
    """
    Expression that must be true for the breakpoint to be triggered.
    """

    id: int
    """Used to identify the condition in stack traces. Should match breakpoint ID."""

    expression: str
    """Python expression that must evaluate to True for the breakpoint to be triggered."""

    _code: CodeType

    def __init__(self, id: int, expression: str):
        self.id = id
        self.expression = expression
        self._code = compile(expression, f"breakpoint-{id}-condition", "eval")

    def test(self, frame: StackFrame) -> bool:
        """
        Returns True if the breakpoint should be triggered in the specified frame.
        """
        try:
            result = eval(
                self._code,
                frame.frame_object.f_globals,
                frame.frame_object.f_locals,
            )
            return bool(result)
        except BaseException as exc:
            log.error(
                f"Exception while evaluating breakpoint condition ({self.expression}): {exc}"
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

    id: int
    """Used to identify the condition in stack traces. Should match breakpoint ID."""

    hit_condition: str
    """Hit count expression."""

    _count: int
    _operator: Callable[[int, int], bool]

    def __init__(self, id: int, hit_condition: str):
        self.id = id
        self.hit_condition = hit_condition
        m = re.match(r"^\D*(\d+)$", hit_condition)
        if not m:
            raise SyntaxError(f"Invalid hit condition: {hit_condition}")
        self._count = int(m.group(2))
        try:
            op = self._OPERATORS[m.group(1) or "=="]
        except KeyError:
            raise SyntaxError(f"Invalid hit condition operator: {op}")
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

    id: int
    """Used to identify the condition in stack traces. Should match breakpoint ID."""

    message: str
    """The message to be logged. May contain expressions in curly braces."""

    _code: CodeType
    """Compiled code object for the f-string corresponding to the message."""

    def __init__(self, id: int, message: str):
        self.id = id
        self.message = message
        f_string = "f" + repr(message)
        self._code = compile(f_string, f"breakpoint-{id}-logMessage", "eval")

    def format(self, frame: StackFrame) -> str:
        """
        Formats the message using the specified frame's locals and globals.
        """
        try:
            return eval(
                self._code, frame.frame_object.f_globals, frame.frame_object.f_locals
            )
        except BaseException as exc:
            log.exception(
                f"Exception while formatting breakpoint log message f{self.message!r}: {exc}"
            )
            return self.message


class Breakpoint:
    """
    Represents a DAP Breakpoint.
    """

    id: int
    source: Source
    line: int
    is_enabled: bool

    condition: Condition | None

    hit_condition: HitCondition | None

    log_message: LogMessage | None

    hit_count: int
    """Number of times this breakpoint has been hit."""

    _all: ClassVar[Dict[int, "Breakpoint"]] = {}

    _at: ClassVar[Dict[Source, Dict[int, List["Breakpoint"]]]] = defaultdict(
        lambda: defaultdict(lambda: [])
    )

    # ID must be explicitly specified so that conditions and log message can
    # use the same ID - this makes for better call stacks and error messages.
    def __init__(
        self,
        id: int,
        source: Source,
        line: int,
        *,
        condition: Condition | None = None,
        hit_condition: HitCondition | None = None,
        log_message: LogMessage | None = None,
    ):
        self.id = id
        self.source = source
        self.line = line
        self.is_enabled = True
        self.condition = condition
        self.hit_condition = hit_condition
        self.log_message = log_message
        self.hit_count = 0

        with _cvar:
            self._all[self.id] = self
            self._at[self.source][self.line].append(self)
            _cvar.notify_all()
        monitoring.restart_events()

    def __getstate__(self) -> dict:
        return {
            "line": self.line,
            "verified": True,  # TODO
        }

    @classmethod
    def at(self, source: Source, line: int) -> List["Breakpoint"]:
        """
        Returns a list of all breakpoints at the specified location.
        """
        with _cvar:
            return self._at[source][line]

    @classmethod
    def clear(self, sources: Iterable[Source] = None):
        """
        Removes all breakpoints in the specified files, or all files if None.
        """
        with _cvar:
            if sources is None:
                sources = list(self._at.keys())
            for source in sources:
                bps_in = self._at.pop(source, {}).values()
                for bps_at in bps_in:
                    for bp in bps_at:
                        del self._all[bp.id]
            _cvar.notify_all()
        monitoring.restart_events()

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
            # Check source last since path resolution is potentially expensive.
            if (
                not self.is_enabled
                or frame.line != self.line
                or frame.source() != self.source
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
