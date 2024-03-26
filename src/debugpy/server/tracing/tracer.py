# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import gc
import inspect
import sys
import threading
import traceback
from debugpy import server
from debugpy.server.tracing import (
    Breakpoint,
    ExceptionBreakMode,
    ExceptionInfo,
    Source,
    StackFrame,
    Step,
    Thread,
    _cvar,
    is_internal_python_frame,
)
from sys import monitoring
from types import CodeType, FrameType, TracebackType
from typing import Iterable, Literal, Type


class Log:
    """
    Safe logging for Tracer. Delegates to debugpy.common.log, but only when it is
    safe to do so (i.e. not during finalization).
    """

    def __init__(self):
        import atexit
        from debugpy.common import log

        def nop(*args, **kwargs):
            pass

        @atexit.register
        def disable():
            self.debug = self.info = self.warning = self.error = self.exception = nop

        self.debug = lambda *args, **kwargs: log.debug("{0}", *args, **kwargs)
        self.info = lambda *args, **kwargs: log.info("{0}", *args, **kwargs)
        self.warning = lambda *args, **kwargs: log.warning("{0}", *args, **kwargs)
        self.error = lambda *args, **kwargs: log.error("{0}", *args, **kwargs)
        self.exception = lambda *args, **kwargs: log.exception("{0}", *args, **kwargs)

        #self.debug = nop  # TODO: improve logging performance enough to enable this.


log = Log()
del Log


# Unhandled exceptions are reported via sys.excepthook & threading.excepthook, which
# aren't sys.monitoring callbacks; thus, they are traced by sys.monitoring like any
# other code. To avoid issues stemming from that, our excepthook wraps the original
# unhandled exception into an instance of this class and re-raises it, which can then
# be processed by _trace_raise like all other exceptions.
class UnhandledException(Exception):
    """
    Raised when an exception is not handled by any of the registered handlers.
    """

    exception: BaseException

    def __init__(self, exc: BaseException):
        self.exception = exc


class Tracer:
    """
    Singleton that manages sys.monitoring callbacks for this process.
    """

    CONTROL_FLOW_EXCEPTIONS = (StopIteration, StopAsyncIteration, GeneratorExit)
    """
    Exception types that are used by Python itself to implement control flow in loops
    and generators. Reporting these exceptions would be extremely chatty and serve no
    useful purpose, so they are always ignored unless unhandled.
    """

    exception_break_mode: ExceptionBreakMode

    _stopped_by: Thread | None
    """
    If not None, indicates the thread on which the event that caused the debuggee
    to enter suspended state has occurred. When any other thread observes a non-None
    value of this attribute, it must immediately suspend and wait until it is cleared.
    """

    _steps: dict[Thread, Step]
    """Ongoing steps, keyed by thread."""

    def __init__(self):
        self.log = log
        self.exception_break_mode = ExceptionBreakMode.NEVER
        self._stopped_by = None
        self._steps = {}

        # sys.monitoring callbacks may be invoked during finalization, in which case
        # they need access to these identifiers to detect that and abort early. However,
        # module globals are removed during finalization, so we need to preload these
        # into member variables to ensure they are still accessible.
        self.sys = sys
        self.DISABLE = monitoring.DISABLE

    @property
    def adapter(self):
        return server.adapter()

    def start(self):
        """
        Register sys.monitoring tracing callbacks.
        """

        log.info("Registering sys.monitoring tracing callbacks...")

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
            monitoring.events.LINE: self._trace_line,
            monitoring.events.PY_START: self._trace_py_start,
            monitoring.events.PY_RESUME: self._trace_py_resume,
            monitoring.events.PY_RETURN: self._trace_py_return,
            monitoring.events.PY_YIELD: self._trace_py_yield,
            monitoring.events.PY_THROW: self._trace_py_throw,
            monitoring.events.PY_UNWIND: self._trace_py_unwind,
            monitoring.events.RAISE: self._trace_raise,
            monitoring.events.RERAISE: self._trace_reraise,
            monitoring.events.EXCEPTION_HANDLED: self._trace_exception_handled,
        }
        for event, func in trace_funcs.items():
            monitoring.register_callback(monitoring.DEBUGGER_ID, event, func)

        self._old_sys_excepthook = sys.excepthook
        sys.excepthook = self._sys_excepthook

        self._old_threading_excepthook = threading.excepthook
        threading.excepthook = self._threading_excepthook

        log.info("sys.monitoring tracing callbacks registered.")

    def pause(self):
        """
        Pause all threads.
        """
        log.info("Pausing all threads.")
        with _cvar:
            # Although "pause" is a user-induced scenario that is not specifically
            # associated with any thread, we still need to pick some thread that
            # will nominally own it to report the event on. If there is a designated
            # main thread in the process, use that, otherwise pick one at random.
            python_thread = threading.main_thread()
            if python_thread is None:
                python_thread = next(iter(threading.enumerate()), None)
                if python_thread is None:
                    raise ValueError("No threads to pause.")
            thread = Thread.from_python_thread(python_thread)
            self._begin_stop(thread, "pause")

    def resume(self):
        """
        Resume all threads.
        """
        log.info("Resuming all threads.")
        self._end_stop()

    def abandon_step(self, threads: Iterable[int] = None):
        """
        Abandon any ongoing steps that are in progress on the specified threads
        (all threads if argument is None).
        """
        with _cvar:
            if threads is None:
                step = self._steps.clear()
                while self._steps:
                    thread, step = self._steps.popitem()
                    log.info(f"Abandoned {step} on {thread}.")
            else:
                for thread in threads:
                    step = self._steps.pop(thread, None)
                    if step is not None:
                        log.info(f"Abandoned {step} on {thread}.")
            _cvar.notify_all()
        monitoring.restart_events()

    def step_in(self, thread: Thread):
        """
        Step into the next statement executed by the specified thread.
        """
        log.info(f"Step in on {thread}.")
        with _cvar:
            self._steps[thread] = Step("in")
            self._end_stop()
        monitoring.restart_events()

    def step_out(self, thread: Thread):
        """
        Step out of the current function executed by the specified thread.
        """
        log.info(f"Step out on {thread}.")
        with _cvar:
            self._steps[thread] = Step("out")
            self._end_stop()
        monitoring.restart_events()

    def step_over(self, thread: Thread):
        log.info(f"Step over on {thread}.")
        """
        Step over the next statement executed by the specified thread.
        """
        with _cvar:
            self._steps[thread] = Step("over")
            self._end_stop()
        monitoring.restart_events()

    def _begin_stop(
        self,
        thread: Thread,
        reason: str,
        hit_breakpoints: Iterable[Breakpoint] = (),
    ):
        """
        Report the stop to the adapter and tell all threads to suspend themselves.
        """

        with _cvar:
            self._stopped_by = thread
            _cvar.notify_all()
            monitoring.restart_events()
        self.adapter.channel.send_event(
            "stopped",
            {
                "reason": reason,
                "threadId": thread.id,
                "allThreadsStopped": True,
                "hitBreakpointIds": [bp.id for bp in hit_breakpoints],
            },
        )

    def _end_stop(self):
        """
        Tell all threads to resume themselves.
        """
        with _cvar:
            self._stopped_by = None
            _cvar.notify_all()

    def _this_thread(self) -> Thread | None:
        """
        Returns the DAP Thread object for the current thread, or None if interpreter
        is shutting down.
        """
        return (
            None
            if self.sys.is_finalizing()
            else Thread.from_python_thread(threading.current_thread())
        )

    def _suspend_this_thread(self, python_frame: FrameType):
        """
        Suspends execution of this thread until the current stop ends.
        """

        thread = self._this_thread()
        with _cvar:
            if self._stopped_by is None:
                return

            log.info(f"{thread} suspended.")
            thread.current_frame = python_frame
            while self._stopped_by is not None:
                _cvar.wait()
            thread.current_frame = None
            log.info(f"{thread} resumed.")
            StackFrame.invalidate(thread)
            gc.collect()

            step = self._steps.get(thread, None)
            if step is not None and step.origin is None:
                # This step has just begun - update the Step object with information
                # about current frame that will be used to track step completion.
                step.origin = python_frame
                step.origin_line = python_frame.f_lineno

    def _trace_line(self, code: CodeType, line_number: int):
        thread = self._this_thread()
        if thread is None or not thread.is_traced:
            return self.DISABLE

        log.debug(f"sys.monitoring event: LINE({line_number}, {code})")

        # These two local variables hold direct or indirect references to frame
        # objects on the stack of the current thread, and thus must be cleaned up
        # on exit to avoid expensive GC cycles.
        python_frame = inspect.currentframe().f_back
        frame = None
        try:
            with _cvar:
                step = self._steps.get(thread, None)
                is_stepping = step is not None and step.origin is not None
                if not is_stepping:
                    log.debug(f"No step in progress on {thread}.")
                else:
                    log.debug(
                        f"Tracing {step} originating from {step.origin} on {thread}."
                    )
                    if step.is_complete(python_frame):
                        log.info(f"{step} finished on thread {thread}.")
                        del self._steps[thread]
                        self._begin_stop(thread, "step")

                if self._stopped_by is not None:
                    # Even if this thread is suspending, any debugpy internal code on it should
                    # keep running until it returns to user code; otherwise, it may deadlock
                    # if it was holding e.g. a messaging lock.
                    if not is_internal_python_frame(python_frame):
                        self._suspend_this_thread(python_frame)
                        return

                log.debug(f"Resolving path {code.co_filename!r}...")
                source = Source(code.co_filename)
                log.debug(f"Path {code.co_filename!r} resolved to {source}.")

                bps = Breakpoint.at(source, line_number)
                if not bps and not is_stepping:
                    log.debug(f"No breakpoints at {source}:{line_number}.")
                    return self.DISABLE
                log.debug(
                    f"Considering breakpoints: {[bp.__getstate__() for bp in bps]}."
                )

                frame = StackFrame(thread, python_frame)
                stop_bps = []
                for bp in bps:
                    match bp.is_triggered(frame):
                        case str() as message:
                            # Triggered, has logMessage - print it but don't stop.
                            self.adapter.channel.send_event(
                                "output",
                                {
                                    "category": "console",
                                    "output": message,
                                    "line": line_number,
                                    "source": source,
                                },
                            )
                        case triggered if triggered:
                            # Triggered, no logMessage - stop.
                            stop_bps.append(bp)
                        case _:
                            continue

                if stop_bps:
                    log.info(
                        f"Stack frame {frame} stopping at breakpoints {[bp.__getstate__() for bp in stop_bps]}."
                    )
                    self._begin_stop(thread, "breakpoint", stop_bps)
                    self._suspend_this_thread(frame.python_frame)
        finally:
            del frame
            del python_frame

    def _process_exception(
        self,
        exc: BaseException,
        thread: Thread,
        origin: Literal["raise", "reraise", "excepthook"],
    ):
        if isinstance(exc, UnhandledException):
            exc = exc.exception
            origin = "excepthook"

        # These two local variables hold direct or indirect references to frame
        # objects on the stack of the current thread, and thus must be cleaned up
        # on exit to avoid expensive GC cycles.
        python_frame = inspect.currentframe().f_back
        frame = None
        try:
            stop = False
            match self.exception_break_mode:
                case ExceptionBreakMode.ALWAYS:
                    stop = origin == "raise"
                case ExceptionBreakMode.UNHANDLED:
                    stop = origin == "excepthook"
                    if stop:
                        # The stack trace is already unwound, and reporting it as empty
                        # would be useless. Instead, we want to report it as t was at the
                        # point where the exception was raised, so walk the traceback all
                        # the way back to the originating frame.
                        if exc.__traceback__ is not None:
                            for python_frame, _ in traceback.walk_tb(exc.__traceback__):
                                pass

            if stop:
                thread.current_exception = ExceptionInfo(exc, self.exception_break_mode)
                self._begin_stop(thread, "exception")
                self._suspend_this_thread(python_frame)
                thread.current_exception = None

        finally:
            del frame
            del python_frame

    def _trace_raise(self, code: CodeType, ip: int, exc: BaseException):
        if isinstance(exc, self.CONTROL_FLOW_EXCEPTIONS):
            return
        thread = self._this_thread()
        if thread is None or not thread.is_traced:
            return
        log.debug(
            f"sys.monitoring event: RAISE({code}, {ip}, {type(exc).__qualname__})"
        )
        self._process_exception(exc, thread, "raise")

    def _trace_reraise(self, code: CodeType, ip: int, exc: BaseException):
        if isinstance(exc, self.CONTROL_FLOW_EXCEPTIONS):
            return
        thread = self._this_thread()
        if thread is None or not thread.is_traced:
            return
        log.debug(
            f"sys.monitoring event: RERAISE({code}, {ip}, {type(exc).__qualname__})"
        )
        self._process_exception(exc, thread, "reraise")

    def _sys_excepthook(
        self, exc_type: Type, exc: BaseException, tb: TracebackType
    ):
        thread = self._this_thread()
        if thread is None or not thread.is_traced:
            return
        log.debug(f"sys.excepthook({exc_type}, {exc})")
        try:
            # delegate to _trace_raise
            raise UnhandledException(exc)
        except:
            pass
        return self._old_sys_excepthook(exc_type, exc, tb)

    def _threading_excepthook(self, args):
        thread = self._this_thread()
        if thread is None or not thread.is_traced:
            return
        exc_type = args.exc_type
        exc = args.exc_value
        log.debug(f"threading.excepthook({exc_type}, {exc})")
        try:
            # delegate to _trace_raise
            raise UnhandledException(exc)
        except:
            pass
        return self._old_threading_excepthook(args)

    def _trace_py_start(self, code: CodeType, ip: int):
        thread = self._this_thread()
        if thread is None or not thread.is_traced:
            return self.DISABLE
        log.debug(f"sys.monitoring event: PY_START({code}, {ip})")

    def _trace_py_resume(self, code: CodeType, ip: int):
        thread = self._this_thread()
        if thread is None or not thread.is_traced:
            return self.DISABLE
        log.debug(f"sys.monitoring event: PY_RESUME({code}, {ip})")

    def _trace_py_return(self, code: CodeType, ip: int, retval: object):
        thread = self._this_thread()
        if thread is None or not thread.is_traced:
            return self.DISABLE
        log.debug(f"sys.monitoring event: PY_RETURN({code}, {ip})")
        # TODO: capture returned value to report it when client requests locals.
        pass

    def _trace_py_yield(self, code: CodeType, ip: int, retval: object):
        thread = self._this_thread()
        if thread is None or not thread.is_traced:
            return self.DISABLE
        log.debug(f"sys.monitoring event: PY_YIELD({code}, {ip})")
        # TODO: capture yielded value to report it when client requests locals.
        pass

    def _trace_py_throw(self, code: CodeType, ip: int, exc: BaseException):
        thread = self._this_thread()
        if thread is None or not thread.is_traced:
            return
        log.debug(
            f"sys.monitoring event: PY_THROW({code}, {ip}, {type(exc).__qualname__})"
        )

    def _trace_py_unwind(self, code: CodeType, ip: int, exc: BaseException):
        thread = self._this_thread()
        if thread is None or not thread.is_traced:
            return
        log.debug(
            f"sys.monitoring event: PY_UNWIND({code}, {ip}, {type(exc).__qualname__})"
        )

    def _trace_exception_handled(self, code: CodeType, ip: int, exc: BaseException):
        thread = self._this_thread()
        if thread is None or not thread.is_traced:
            return
        log.debug(
            f"sys.monitoring event: EXCEPTION_HANDLED({code}, {ip}, {type(exc).__qualname__})"
        )

tracer = Tracer()
del Tracer
