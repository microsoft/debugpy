# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

# Once callbacks are registered they are invoked even during finalization when the
# Python is shutting down. Thus, trace_* methods, and any other methods that they
# invoke, must not use any globals from this or other modules (including globals
# that represent imported modules or defined classes!) until it checks that they
# are present, or preload them into class or instance attributes in advance.
# To facilitate this, Tracer is defined in a separate submodule which should not
# contain ANY top-level imports other than typing nor definitions other than the
# class itself. All other imports must be done in class scope and then referred to
# from methods via self.

from types import CodeType, FrameType
from typing import Iterable


class Log:
    """
    Safe logging for Tracer. Delegates to debugpy.common.log, but only when it is
    safe to do so (i.e. not during finalization).
    """

    from debugpy.common import log

    def __init__(self):
        import atexit

        def nop(*args, **kwargs):
            pass

        @atexit.register
        def disable():
            self.debug = self.info = self.warning = self.error = self.exception = nop

    def debug(self, *args, **kwargs):
        # TODO: improve logging performance enough to enable this.
        # self.log.debug("{0}", *args, **kwargs)
        # print(*args)
        pass

    def info(self, *args, **kwargs):
        self.log.info("{0}", *args, **kwargs)

    def warning(self, *args, **kwargs):
        self.log.warning("{0}", *args, **kwargs)

    def error(self, *args, **kwargs):
        self.log.error("{0}", *args, **kwargs)

    def exception(self, *args, **kwargs):
        self.log.exception("{0}", *args, **kwargs)


class Tracer:
    """
    Singleton that manages sys.monitoring callbacks for this process.
    """

    import inspect
    import threading
    from debugpy import server
    from debugpy.server.tracing import (
        Breakpoint,
        Source,
        Step,
        Thread,
        StackFrame,
        _cvar,
    )
    from sys import monitoring

    instance: "Tracer"

    log: Log

    _stopped_by: Thread | None = None
    """
    If not None, indicates the thread on which the event that caused the debuggee
    to enter suspended state has occurred. When any other thread observes a non-None
    value of this attribute, it must immediately suspend and wait until it is cleared.
    """

    _steps: dict[Thread, Step] = {}
    """Ongoing steps, keyed by thread."""

    def __init__(self):
        self.log = Log()

    @property
    def adapter(self):
        return self.server.adapter()

    def start(self):
        """
        Register sys.monitoring tracing callbacks.
        """

        self.log.info("Registering sys.monitoring tracing callbacks...")

        self.monitoring.use_tool_id(self.monitoring.DEBUGGER_ID, "debugpy")
        self.monitoring.set_events(
            self.monitoring.DEBUGGER_ID,
            (
                self.monitoring.events.LINE
                | self.monitoring.events.PY_START
                | self.monitoring.events.PY_RETURN
                | self.monitoring.events.PY_RESUME
                | self.monitoring.events.PY_YIELD
                | self.monitoring.events.PY_THROW
                | self.monitoring.events.PY_UNWIND
                | self.monitoring.events.RAISE
                | self.monitoring.events.RERAISE
                | self.monitoring.events.EXCEPTION_HANDLED
            ),
        )
        trace_funcs = {
            self.monitoring.events.LINE: self._trace_line,
            self.monitoring.events.PY_START: self._trace_py_start,
            self.monitoring.events.PY_RESUME: self._trace_py_resume,
            self.monitoring.events.PY_RETURN: self._trace_py_return,
            self.monitoring.events.PY_YIELD: self._trace_py_yield,
            self.monitoring.events.PY_THROW: self._trace_py_throw,
            self.monitoring.events.PY_UNWIND: self._trace_py_unwind,
            self.monitoring.events.RAISE: self._trace_raise,
            self.monitoring.events.RERAISE: self._trace_reraise,
            self.monitoring.events.EXCEPTION_HANDLED: self._trace_exception_handled,
        }
        for event, func in trace_funcs.items():
            self.monitoring.register_callback(self.monitoring.DEBUGGER_ID, event, func)

        self.log.info("sys.monitoring tracing callbacks registered.")

    def pause(self):
        """
        Pause all threads.
        """
        self.log.info("Pausing all threads.")
        with self._cvar:
            # Although "pause" is a user-induced scenariop that is not specifically
            # associated with any thread, we still need to pick some thread that
            # will nominally own it to report the event on. If there is a designated
            # main thread in the process, use that, otherwise pick one at random.
            python_thread = self.threading.main_thread()
            if python_thread is None:
                python_thread = next(iter(self.threading.enumerate()), None)
                if python_thread is None:
                    raise ValueError("No threads to pause.")
            thread = self.Thread.from_python_thread(python_thread)
            self.begin_stop(thread, "pause")

    def resume(self):
        """
        Resume all threads.
        """
        self.log.info("Resuming all threads.")
        self.end_stop()

    def abandon_step(self, threads: Iterable[int] = None):
        """
        Abandon any ongoing steps that are in progress on the specified threads
        (all threads if argument is None).
        """
        with self._cvar:
            if threads is None:
                step = self._steps.clear()
                while self._steps:
                    thread, step = self._steps.popitem()
                    self.log.info(f"Abandoned {step} on {thread}.")
            else:
                for thread in threads:
                    step = self._steps.pop(thread, None)
                    if step is not None:
                        self.log.info(f"Abandoned {step} on {thread}.")
            self._cvar.notify_all()
        self.monitoring.restart_events()

    def step_in(self, thread: Thread):
        """
        Step into the next statement executed by the specified thread.
        """
        self.log.info(f"Step in on {thread}.")
        with self._cvar:
            self._steps[thread] = self.Step("in")
            self.end_stop()
        self.monitoring.restart_events()

    def step_out(self, thread: Thread):
        """
        Step out of the current function executed by the specified thread.
        """
        self.log.info(f"Step out on {thread}.")
        with self._cvar:
            self._steps[thread] = self.Step("out")
            self.end_stop()
        self.monitoring.restart_events()

    def step_over(self, thread: Thread):
        self.log.info(f"Step over on {thread}.")
        """
        Step over the next statement executed by the specified thread.
        """
        with self._cvar:
            self._steps[thread] = self.Step("over")
            self.end_stop()
        self.monitoring.restart_events()

    def begin_stop(
        self, thread: Thread, reason: str, hit_breakpoints: Iterable[Breakpoint] = ()
    ):
        """
        Report the stop to the adapter and tell all threads to suspend themselves.
        """

        with self._cvar:
            self._stopped_by = thread
            self._cvar.notify_all()
            self.monitoring.restart_events()
        self.adapter.channel.send_event(
            "stopped",
            {
                "reason": reason,
                "threadId": thread.id,
                "allThreadsStopped": True,
                "hitBreakpointIds": [bp.id for bp in hit_breakpoints],
            },
        )

    def end_stop(self):
        """
        Tell all threads to resume themselves.
        """
        with self._cvar:
            self._stopped_by = None
            self._cvar.notify_all()

    def suspend_this_thread(self, frame_obj: FrameType):
        """
        Suspends execution of this thread until the current stop ends.
        """

        thread = self.Thread.from_python_thread()
        with self._cvar:
            if self._stopped_by is None:
                return

            self.log.info(f"{thread} suspended.")
            thread.python_frame = frame_obj
            while self._stopped_by is not None:
                self._cvar.wait()
            thread.python_frame = None
            self.log.info(f"{thread} resumed.")

            step = self._steps.get(thread, None)
            if step is not None and step.origin is None:
                # This step has just begun - update the Step object with information
                # about current frame that will be used to track step completion.
                step.origin = frame_obj
                step.origin_line = frame_obj.f_lineno

    def _trace_line(self, code: CodeType, line_number: int):
        thread = self.Thread.from_python_thread()
        if thread is None or not thread.is_traced:
            return self.monitoring.DISABLE

        self.log.debug(f"sys.monitoring event: LINE({line_number}, {code})")

        # These two local variables hold direct or indirect references to frame
        # objects on the stack of the current thread, and thus must be cleaned up
        # on exit to avoid expensive GC cycles.
        python_frame = self.inspect.currentframe().f_back
        frame = None
        try:
            with self._cvar:
                step = self._steps.get(thread, None)
                is_stepping = step is not None and step.origin is not None
                if not is_stepping:
                    self.log.debug(f"No step in progress on {thread}.")
                else:
                    self.log.debug(
                        f"Tracing {step} originating from {step.origin} on {thread}."
                    )
                    if step.is_complete(python_frame):
                        self.log.info(f"{step} finished on thread {thread}.")
                        del self._steps[thread]
                        self.begin_stop(thread, "step")

                if self._stopped_by is not None:
                    # Even if this thread is pausing, any debugpy internal code on it should
                    # keep running until it returns to user code; otherwise, it may deadlock
                    # if it was holding e.g. a messaging lock.
                    if not python_frame.f_globals.get("__name__", "").startswith(
                        "debugpy"
                    ):
                        self.suspend_this_thread(python_frame)
                        return

                self.log.debug(f"Resolving path {code.co_filename!r}...")
                source = self.Source(code.co_filename)
                self.log.debug(f"Path {code.co_filename!r} resolved to {source}.")

                bps = self.Breakpoint.at(source, line_number)
                if not bps and not is_stepping:
                    self.log.debug(f"No breakpoints at {source}:{line_number}.")
                    return self.monitoring.DISABLE
                self.log.debug(
                    f"Considering breakpoints: {[bp.__getstate__() for bp in bps]}."
                )

                frame = self.StackFrame(thread, self.inspect.currentframe().f_back)
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
                    self.log.info(
                        f"Stack frame {frame} stopping at breakpoints {[bp.__getstate__() for bp in stop_bps]}."
                    )
                    self.begin_stop(thread, "breakpoint", stop_bps)
                    self.suspend_this_thread(frame.frame_object)
        finally:
            del frame
            del python_frame

    def _trace_py_start(self, code: CodeType, ip: int):
        thread = self.Thread.from_python_thread()
        if thread is None or not thread.is_traced:
            return self.monitoring.DISABLE
        self.log.debug(f"sys.monitoring event: PY_START({code}, {ip})")

    def _trace_py_resume(self, code: CodeType, ip: int):
        thread = self.Thread.from_python_thread()
        if thread is None or not thread.is_traced:
            return self.monitoring.DISABLE
        self.log.debug(f"sys.monitoring event: PY_RESUME({code}, {ip})")

    def _trace_py_return(self, code: CodeType, ip: int, retval: object):
        thread = self.Thread.from_python_thread()
        if thread is None or not thread.is_traced:
            return self.monitoring.DISABLE
        self.log.debug(f"sys.monitoring event: PY_RETURN({code}, {ip})")
        # TODO: capture returned value to report it when client requests locals.
        pass

    def _trace_py_yield(self, code: CodeType, ip: int, retval: object):
        thread = self.Thread.from_python_thread()
        if thread is None or not thread.is_traced:
            return self.monitoring.DISABLE
        self.log.debug(f"sys.monitoring event: PY_YIELD({code}, {ip})")
        # TODO: capture yielded value to report it when client requests locals.
        pass

    def _trace_py_throw(self, code: CodeType, ip: int, exc: BaseException):
        thread = self.Thread.from_python_thread()
        if thread is None or not thread.is_traced:
            return
        self.log.debug(
            f"sys.monitoring event: PY_THROW({code}, {ip}, {type(exc).__qualname__})"
        )

    def _trace_py_unwind(self, code: CodeType, ip: int, exc: BaseException):
        thread = self.Thread.from_python_thread()
        if thread is None or not thread.is_traced:
            return
        self.log.debug(
            f"sys.monitoring event: PY_UNWIND({code}, {ip}, {type(exc).__qualname__})"
        )

    def _trace_raise(self, code: CodeType, ip: int, exc: BaseException):
        thread = self.Thread.from_python_thread()
        if thread is None or not thread.is_traced:
            return
        self.log.debug(
            f"sys.monitoring event: RAISE({code}, {ip}, {type(exc).__qualname__})"
        )

    def _trace_reraise(self, code: CodeType, ip: int, exc: BaseException):
        thread = self.Thread.from_python_thread()
        if thread is None or not thread.is_traced:
            return
        self.log.debug(
            f"sys.monitoring event: RERAISE({code}, {ip}, {type(exc).__qualname__})"
        )

    def _trace_exception_handled(self, code: CodeType, ip: int, exc: BaseException):
        thread = self.Thread.from_python_thread()
        if thread is None or not thread.is_traced:
            return
        self.log.debug(
            f"sys.monitoring event: EXCEPTION_HANDLED({code}, {ip}, {type(exc).__qualname__})"
        )


Tracer.instance = Tracer()
