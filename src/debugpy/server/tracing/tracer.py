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
    from debugpy.server.tracing import Breakpoint, Step, Thread, StackFrame, _cvar
    from pathlib import Path
    from sys import monitoring

    instance: "Tracer"

    log: Log

    _pause_ids = set()
    """IDs of threads that are currently pausing or paused."""

    _steps = {}
    """Ongoing steps, keyed by thread ID."""

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

    def pause(self, thread_ids: Iterable[int] = None):
        """
        Pause the specified threads, or all threads if thread_ids is None.
        """
        if thread_ids is None:
            # Pausing is async, so additional threads may be spawned even as we are
            # trying to pause the ones we currently know about; iterate until all
            # known threads are paused, and no new threads appear.
            while True:
                thread_ids = {thread.id for thread in self.Thread.enumerate()}
                if self._pause_ids.keys() == thread_ids:
                    return
                self.pause(thread_ids)
        else:
            self.log.info(f"Pausing threads: {thread_ids}")
            with self._cvar:
                self._pause_ids.update(thread_ids)
                self._cvar.notify_all()
            self.monitoring.restart_events()

    def resume(self, thread_ids: Iterable[int] = None):
        """
        Resume the specified threads, or all threads if thread_ids is None.
        """
        with self._cvar:
            if thread_ids is None:
                self.log.info("Resuming all threads.")
                self._pause_ids.clear()
            else:
                self.log.info(f"Resuming threads: {thread_ids}")
                self._pause_ids.difference_update(thread_ids)
            self._cvar.notify_all()
        self.monitoring.restart_events()

    def abandon_step(self, thread_ids: Iterable[int] = None):
        """
        Abandon any ongoing steps that are in progress on the specified threads
        (all threads if thread_ids is None).
        """
        with self._cvar:
            if thread_ids is None:
                thread_ids = [thread.id for thread in self.Thread.enumerate()]
            for thread_id in thread_ids:
                step = self._steps.pop(thread_id, None)
                if step is not None:
                    self.log.info(f"Abandoned step-{step.step} on {thread_id}.")
            self._cvar.notify_all()
        self.monitoring.restart_events()

    def step_in(self, thread_id: int):
        """
        Step into the next statement executed by the specified thread.
        """
        self.log.info(f"Step in on thread {thread_id}.")
        with self._cvar:
            self._steps[thread_id] = self.Step("in")
            self._pause_ids.clear()
            self._cvar.notify_all()
        self.monitoring.restart_events()

    def step_out(self, thread_id: int):
        """
        Step out of the current function executed by the specified thread.
        """
        self.log.info(f"Step out on thread {thread_id}.")
        with self._cvar:
            self._steps[thread_id] = self.Step("out")
            self._pause_ids.clear()
            self._cvar.notify_all()
        self.monitoring.restart_events()

    def step_over(self, thread_id: int):
        self.log.info(f"Step over on thread {thread_id}.")
        """
        Step over the next statement executed by the specified thread.
        """
        with self._cvar:
            self._steps[thread_id] = self.Step("over")
            self._pause_ids.clear()
            self._cvar.notify_all()
        self.monitoring.restart_events()

    def _stop(
        self,
        frame_obj: FrameType,
        reason: str,
        hit_breakpoints: Iterable[Breakpoint] = (),
    ):
        thread = self.Thread.from_python_thread()
        self.log.info(f"Pausing thread {thread.id}: {reason}.")

        with self._cvar:
            if thread.id not in self._pause_ids:
                return

            self.adapter.channel.send_event(
                "stopped",
                {
                    "reason": reason,
                    "threadId": thread.id,
                    "allThreadsStopped": False,  # TODO
                    "hitBreakpointIds": [bp.id for bp in hit_breakpoints],
                },
            )

            self.log.info(f"Thread {thread.id} paused.")
            while thread.id in self._pause_ids:
                self._cvar.wait()
            self.log.info(f"Thread {thread.id} unpaused.")

            step = self._steps.get(thread.id, None)
            if step is not None and step.origin is None:
                step.origin = frame_obj
                step.origin_line = frame_obj.f_lineno

    def _trace_line(self, code: CodeType, line_number: int):
        thread = self.Thread.from_python_thread()
        if not thread.is_traced:
            return self.monitoring.DISABLE

        self.log.debug(f"sys.monitoring event: LINE({line_number}, {code})")
        frame_obj = self.inspect.currentframe().f_back

        stop_reason = None
        with self._cvar:
            if thread.id in self._pause_ids:
                stop_reason = "pause"

            step = self._steps.get(thread.id, None)
            is_stepping = step is not None and step.origin is not None
            if not is_stepping:
                self.log.debug(f"No step in progress on thread {thread.id}.")
            else:
                self.log.debug(
                    f"Tracing step-{step.step} originating from {step.origin} on thread {thread.id}."
                )

                # TODO: use CALL/RETURN/PY_RETURN to track these more efficiently.
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
                        if (
                            frame_obj is step.origin
                            and frame_obj.f_lineno == step.origin_line
                        ):
                            step_finished = False
                            break
                        frame_obj = frame_obj.f_back
                else:
                    raise ValueError(f"Unknown step type: {step.step}")

                if step_finished:
                    self.log.info(f"Step-{step.step} finished on thread {thread.id}.")
                    del self._steps[thread.id]
                    self._pause_ids.add(thread.id)
                    self._cvar.notify_all()
                    stop_reason = "step"

        if stop_reason is not None:
            # Even if this thread is pausing, any debugpy internal code on it should
            # keep running until it returns to user code; otherwise, it may deadlock
            # if it was holding e.g. a messaging lock.
            print(frame_obj.f_globals.get("__name__"))
            if not frame_obj.f_globals.get("__name__", "").startswith("debugpy"):
                return self._stop(frame_obj, stop_reason)

        self.log.debug(f"Resolving path {code.co_filename!r}...")
        path = self.Path(code.co_filename)
        try:
            path = path.resolve()
        except (OSError, RuntimeError):
            pass
        self.log.debug(f"Path {code.co_filename!r} resolved to {path}.")

        bps = self.Breakpoint.at(path, line_number)
        if not bps and not is_stepping:
            self.log.debug(f"No breakpoints at {path}:{line_number}.")
            return self.monitoring.DISABLE
        self.log.debug(f"Considering breakpoints: {[bp.__getstate__() for bp in bps]}.")

        frame = self.StackFrame(thread, self.inspect.currentframe().f_back)
        try:
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
                                "source": {"path": path},
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
                with self._cvar:
                    self._pause_ids.add(thread.id)
                    self._cvar.notify_all()
                return self._stop(frame.frame_object, "breakpoint", stop_bps)
        finally:
            del frame

    def _trace_py_start(self, code: CodeType, ip: int):
        thread = self.Thread.from_python_thread()
        if not thread.is_traced:
            return self.monitoring.DISABLE
        self.log.debug(f"sys.monitoring event: PY_START({code}, {ip})")

    def _trace_py_resume(self, code: CodeType, ip: int):
        thread = self.Thread.from_python_thread()
        if not thread.is_traced:
            return self.monitoring.DISABLE
        self.log.debug(f"sys.monitoring event: PY_RESUME({code}, {ip})")

    def _trace_py_return(self, code: CodeType, ip: int, retval: object):
        thread = self.Thread.from_python_thread()
        if not thread.is_traced:
            return self.monitoring.DISABLE
        self.log.debug(f"sys.monitoring event: PY_RETURN({code}, {ip})")
        # TODO: capture returned value to report it when client requests locals.
        pass

    def _trace_py_yield(self, code: CodeType, ip: int, retval: object):
        thread = self.Thread.from_python_thread()
        if not thread.is_traced:
            return self.monitoring.DISABLE
        self.log.debug(f"sys.monitoring event: PY_YIELD({code}, {ip})")
        # TODO: capture yielded value to report it when client requests locals.
        pass

    def _trace_py_throw(self, code: CodeType, ip: int, exc: BaseException):
        thread = self.Thread.from_python_thread()
        if not thread.is_traced:
            return
        self.log.debug(
            f"sys.monitoring event: PY_THROW({code}, {ip}, {type(exc).__qualname__})"
        )

    def _trace_py_unwind(self, code: CodeType, ip: int, exc: BaseException):
        thread = self.Thread.from_python_thread()
        if not thread.is_traced:
            return
        self.log.debug(
            f"sys.monitoring event: PY_UNWIND({code}, {ip}, {type(exc).__qualname__})"
        )

    def _trace_raise(self, code: CodeType, ip: int, exc: BaseException):
        thread = self.Thread.from_python_thread()
        if not thread.is_traced:
            return
        self.log.debug(
            f"sys.monitoring event: RAISE({code}, {ip}, {type(exc).__qualname__})"
        )

    def _trace_reraise(self, code: CodeType, ip: int, exc: BaseException):
        thread = self.Thread.from_python_thread()
        if not thread.is_traced:
            return
        self.log.debug(
            f"sys.monitoring event: RERAISE({code}, {ip}, {type(exc).__qualname__})"
        )

    def _trace_exception_handled(self, code: CodeType, ip: int, exc: BaseException):
        thread = self.Thread.from_python_thread()
        if not thread.is_traced:
            return
        self.log.debug(
            f"sys.monitoring event: EXCEPTION_HANDLED({code}, {ip}, {type(exc).__qualname__})"
        )


Tracer.instance = Tracer()
