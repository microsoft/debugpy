# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import inspect
import os
import sys
import threading
from itertools import islice

from debugpy import adapter
from debugpy.adapter import components
from debugpy.common import json, log, messaging, sockets
from debugpy.common.messaging import MessageDict, Request
from debugpy.common.util import IDMap
from debugpy.server import eval, new_dap_id
from debugpy.server.tracing import (
    Breakpoint,
    Condition,
    ExceptionBreakMode,
    HitCondition,
    LogMessage,
    Source,
    StackFrame,
    Thread,
    tracer,
)


class Adapter:
    """Represents the debug adapter connected to this debug server."""

    class Capabilities(components.Capabilities):
        PROPERTIES = {}

    class Expectations(components.Capabilities):
        PROPERTIES = {
            "locale": "en-US",
            "linesStartAt1": True,
            "columnsStartAt1": True,
            "pathFormat": json.enum("path", optional=True),  # we don't support "uri"
        }

    instance = None
    """If debug adapter is connected, the Adapter instance for it; otherwise, None."""

    connected_event = threading.Event()
    """Event that is only set while the debug adapter is connected to this server."""

    channel = None
    """DAP message channel to the adapter."""

    adapter_access_token = None
    """Access token that this server must use to authenticate with the adapter."""

    server_access_token = None
    """Access token that the adapter must use to authenticate with this server."""

    _is_initialized: bool = False
    _has_started: bool = False
    _client_id: str = None
    _capabilities: Capabilities = None
    _expectations: Expectations = None
    _start_request: messaging.Request = None
    _goto_targets_map: IDMap = IDMap(new_dap_id)

    def __init__(self, stream: messaging.JsonIOStream):
        self._is_initialized = False
        self._has_started = False
        self._client_id = None
        self._capabilities = None
        self._expectations = None
        self._start_request = None
        self._tracer = tracer

        self.channel = messaging.JsonMessageChannel(stream, self)
        self.channel.start()

    @classmethod
    def connect(self, host, port) -> "Adapter":
        assert self.instance is None
        log.info("Connecting to adapter at {0}:{1}", host, port)
        sock = sockets.create_client()
        sock.connect((host, port))
        stream = messaging.JsonIOStream.from_socket(sock, "Adapter")
        self.instance = Adapter(stream)
        return self.instance

    def pydevdAuthorize_request(self, request: Request):
        if self.server_access_token is not None:
            server_token = request("debugServerAccessToken", str, optional=True)
            if server_token != self.server_access_token:
                raise request.cant_handle("Invalid access token")
        return {
            "clientAccessToken": self.adapter_access_token,
        }

    def pydevdSystemInfo_request(self, request: Request):
        return {
            "process": {
                "bitness": sys.maxsize.bit_length(),
                "executable": sys.executable,
                "pid": os.getpid(),
                "ppid": os.getppid(),  # FIXME Win32 venv stub
            },
            "platform": {
                "name": sys.platform,
            },
            "python": {
                "version": sys.version,
                "version_info": sys.version_info,
                "implementation": {
                    # TODO
                },
            },
        }

    def initialize_request(self, request: Request):
        if self._is_initialized:
            raise request.isnt_valid("Session is already initialized")

        self._client_id = request("clientID", "")
        self._capabilities = self.Capabilities(None, request)
        self._expectations = self.Expectations(None, request)
        self._is_initialized = True
        return adapter.CAPABILITIES_V2

    def _handle_start_request(self, request: Request):
        if not self._is_initialized:
            raise request.isnt_valid("Session is not initialized")
        if self._start_request is not None:
            raise request.isnt_valid("Session is already started")

        self._start_request = request
        self.channel.send_event("initialized")

        # TODO: fix to comply with DAP spec. The adapter currently expects this
        # non-standard behavior because pydevd does it that way, so the adapter
        # needs to be fixed as well.
        return {}
        return messaging.NO_RESPONSE  # will respond on "configurationDone"

    def launch_request(self, request: Request):
        return self._handle_start_request(request)

    def attach_request(self, request: Request):
        return self._handle_start_request(request)

    def configurationDone_request(self, request: Request):
        if self._start_request is None or self._has_started:
            raise request.cant_handle(
                '"configurationDone" is only allowed during handling of a "launch" '
                'or an "attach" request'
            )

        self._tracer.start()
        self._has_started = True

        request.respond({})
        # _start_request.respond({})
        self.connected_event.set()

        self.channel.send_event(
            "process",
            {
                "name": "Python Debuggee",  # TODO
                "startMethod": self._start_request.command,
                "isLocalProcess": True,
                "systemProcessId": os.getpid(),
                "pointerSize": sys.maxsize.bit_length(),
            },
        )

    def setFunctionBreakpoints_request(self, request: Request):
        # TODO
        return Exception("Function breakpoints are not supported")

    def setExceptionBreakpoints_request(self, request: Request):
        # TODO: "exceptionOptions"

        filters = set(request("filters", json.array(str)))
        if len(filters - {"raised", "uncaught", "userUncaught"}):
            raise request.isnt_valid(
                f"Unsupported exception breakpoint filter: {filter!r}"
            )

        break_mode = ExceptionBreakMode.NEVER
        if "raised" in filters:
            break_mode = ExceptionBreakMode.ALWAYS
        elif "uncaught" in filters:
            break_mode = ExceptionBreakMode.UNHANDLED
        elif "userUncaught" in filters:
            break_mode = ExceptionBreakMode.USER_UNHANDLED
        self._tracer.exception_break_mode = break_mode

        # TODO: return "breakpoints"
        return {}

    def setBreakpoints_request(self, request: Request):
        # TODO: implement source.reference for setting breakpoints in sources for
        # which source code was decompiled or retrieved via inspect.getsource.
        source = Source(request("source", json.object())("path", str))

        # TODO: implement column support.
        # Use dis.get_instruction() to iterate over instructions and corresponding
        # dis.Positions to find the instruction to which the column corresponds,
        # and use monitoring.events.INSTRUCTION rather than LINE.
        # NOTE: needs perf testing to see if INSTRUCTION is too slow even when
        # returning monitoring.DISABLE. Might need to pick LINE or INSTRUCTION based
        # on what's requested. Would be nice to always use INSTRUCTION tho.

        if "breakpoints" in request.arguments:
            bps = list(request("breakpoints", json.array(json.object())))
        else:
            lines = request("lines", json.array(int))
            bps = [MessageDict(request, {"line": line}) for line in lines]

        Breakpoint.clear([source])

        # Do the first pass validating conditions and log messages for syntax errors; if
        # any breakpoint fails validation, we want to respond with an error right away
        # so that user gets immediate feedback, but this also means that we shouldn't
        # actually set any breakpoints until we've validated all of them.
        bps_info = []
        for bp in bps:
            id = new_dap_id()
            line = bp("line", int)

            # A missing condition or log message can be represented as the corresponding
            # property missing, or as the property being present but set to empty string.

            condition = bp("condition", str, optional=True)
            if condition:
                try:
                    condition = Condition(id, condition)
                except SyntaxError as exc:
                    raise request.isnt_valid(
                        f"Syntax error in condition ({condition}): {exc}"
                    )
            else:
                condition = None

            hit_condition = bp("hitCondition", str, optional=True)
            if hit_condition:
                try:
                    hit_condition = HitCondition(id, hit_condition)
                except SyntaxError as exc:
                    raise request.isnt_valid(
                        f"Syntax error in hit condition ({hit_condition}): {exc}"
                    )
            else:
                hit_condition = None

            log_message = bp("logMessage", str, optional=True)
            if log_message:
                try:
                    log_message = LogMessage(id, log_message)
                except SyntaxError as exc:
                    raise request.isnt_valid(
                        f"Syntax error in log message f{log_message!r}: {exc}"
                    )
            else:
                log_message = None

            bps_info.append((id, source, line, condition, hit_condition, log_message))

        # Now that we know all breakpoints are syntactically valid, we can set them.
        bps_set = [
            Breakpoint(
                id,
                source,
                line,
                condition=condition,
                hit_condition=hit_condition,
                log_message=log_message,
            )
            for id, source, line, condition, hit_condition, log_message in bps_info
        ]
        return {"breakpoints": bps_set}

    def threads_request(self, request: Request):
        return {"threads": Thread.enumerate()}

    def stackTrace_request(self, request: Request):
        thread_id = request("threadId", int)
        start_frame = request("startFrame", 0)
        levels = request("levels", int, optional=True)

        thread = Thread.get(thread_id)
        if thread is None:
            raise request.isnt_valid(f'Unknown thread with "threadId":{thread_id}')

        try:
            stack_trace = thread.get_stack_trace()
        except ValueError:
            raise request.isnt_valid(f"Thread {thread_id} is not suspended")

        stop_frame = (
            len(stack_trace) if levels == () or levels == 0 else start_frame + levels
        )
        log.info(f"stackTrace info {start_frame} {stop_frame}")
        frames = None
        try:
            frames = islice(stack_trace, start_frame, stop_frame)
            return {
                "stackFrames": list(frames),
                "totalFrames": len(stack_trace),
            }
        finally:
            del frames

    # For "pause" and "continue" requests, DAP requires a thread ID to be specified,
    # but does not require the adapter to only pause/unpause the specified thread.
    # Visual Studio debug adapter host does not support the ability to pause/unpause
    # only the specified thread, and requires the adapter to always pause/unpause all
    # threads. For "continue" requests, there is a capability flag that the client can
    # use to indicate support for per-thread continuation, but there's no such flag
    # for per-thread pausing. Furethermore, the semantics of unpausing a specific
    # thread after all threads have been paused is unclear in the event the unpaused
    # thread then spawns additional threads. Therefore, we always ignore the "threadId"
    # property and just pause/unpause everything.

    def pause_request(self, request: Request):
        try:
            self._tracer.pause()
        except ValueError:
            raise request.cant_handle("No threads to pause")
        return {}

    def continue_request(self, request: Request):
        self._tracer.resume()
        return {}

    def stepIn_request(self, request: Request):
        # TODO: support "granularity"
        thread_id = request("threadId", int)
        thread = Thread.get(thread_id)
        if thread is None:
            raise request.isnt_valid(f'Unknown thread with "threadId":{thread_id}')
        self._tracer.step_in(thread)
        return {}

    def stepOut_request(self, request: Request):
        # TODO: support "granularity"
        thread_id = request("threadId", int)
        thread = Thread.get(thread_id)
        if thread is None:
            raise request.isnt_valid(f'Unknown thread with "threadId":{thread_id}')
        self._tracer.step_out(thread)
        return {}

    def next_request(self, request: Request):
        thread_id = request("threadId", int)
        thread = Thread.get(thread_id)
        if thread is None:
            raise request.isnt_valid(f'Unknown thread with "threadId":{thread_id}')
        self._tracer.step_over(thread)
        return {}

    def gotoTargets_request(self, request: Request) -> dict:
        source = request("source", json.object())
        path = source("path", str)
        source = Source(path)
        line = request("line", int)
        target_id = self._goto_targets_map.obtain_key((source, line))
        target = {"id": target_id, "label": f"({path}:{line})", "line": line}

        return {"targets": [target]}

    def goto_request(self, request: Request) -> dict:
        thread_id = request("threadId", int)
        thread = Thread.get(thread_id)
        if thread is None:
            return request.isnt_valid(f'Unknown thread with "threadId":{thread_id}')
        target_id = request("targetId", int)
        try:
            source, line = self._goto_targets_map.obtain_value(target_id)
        except KeyError:
            return request.isnt_valid("Invalid targetId for goto")

        # Make sure the thread is in the same source file
        current_path = inspect.getsourcefile(thread.current_frame.f_code)
        current_source = Source(current_path) if current_path is not None else None
        if current_source != source:
            return request.cant_handle(
                f"{source} is not in the same code block as the current frame",
                silent=True,
            )

        # Create a callback for when the goto actually finishes. We don't
        # want to send our response until then.
        def goto_finished(e: Exception | None):
            if e is not None:
                request.cant_handle(
                    f"Line {line} is not in the same code block as the current frame",
                    silent=True,
                )
            else:
                request.respond({})

        self._tracer.goto(thread, source, line, goto_finished)

        # Response will happen when the line_change_callback happens
        return messaging.NO_RESPONSE

    def exceptionInfo_request(self, request: Request):
        thread_id = request("threadId", int)
        thread = Thread.get(thread_id)
        if thread is None:
            raise request.isnt_valid(f'Unknown thread with "threadId":{thread_id}')
        exc_info = thread.current_exception
        if exc_info is None:
            raise request.cant_handle(
                f'No current exception on thread with "threadId":{thread_id}'
            )
        return exc_info.__getstate__()

    def scopes_request(self, request: Request):
        frame_id = request("frameId", int)
        frame = StackFrame.get(frame_id)
        if frame is None:
            # This is fairly common when user quickly resumes after stopping on a breakpoint
            # or an exception, such that "scopes" request from the client gets processed at
            # the point where the frame is already invalidated.
            return request.isnt_valid(f'Invalid "frameId": {frame_id}', silent=True)
        return {"scopes": frame.scopes()}

    def _parse_value_format(
        self, request: Request, property: str = "format", max_length: int = 1024
    ) -> eval.ValueFormat:
        result = eval.ValueFormat(
            hex=False,
            max_length=max_length,  # VSCode limit for tooltips
            truncation_suffix="⌇⋯",
            circular_ref_marker="↻",
        )

        format = request(property, json.object())
        if format == {}:
            return result

        hex = format("hex", bool, optional=True)
        if hex != ():
            result.hex = hex

        max_length = format("debugpy.maxLength", int, optional=True)
        if max_length != ():
            result.max_length = max_length

        truncation_suffix = format("debugpy.truncationSuffix", str, optional=True)
        if truncation_suffix != ():
            result.truncation_suffix = truncation_suffix

        circular_ref_marker = format("debugpy.circularRefMarker", str, optional=True)
        if circular_ref_marker != ():
            result.circular_ref_marker = circular_ref_marker

        return result

    def _parse_name_format(self, request: Request) -> eval.ValueFormat:
        return self._parse_value_format(request, "debugpy.nameFormat", max_length=32)

    def variables_request(self, request: Request):
        name_format = self._parse_name_format(request)
        value_format = self._parse_value_format(request)
        start = request("start", 0)
        if start < 0:
            return request.isnt_valid(f'Invalid "start": {start}')

        count = request("count", int, optional=True)
        if count == ():
            count = None

        filter = request("filter", str, optional=True)
        match filter:
            case ():
                filter = {"named", "indexed"}
            case "named" | "indexed":
                filter = {filter}
            case _:
                return request.isnt_valid(f'Invalid "filter": {filter!r}')

        container_id = request("variablesReference", int)
        container = eval.VariableContainer.get(container_id)
        if container is None:
            return request.isnt_valid(f'Invalid "variablesReference": {container_id}')

        return {
            "variables": list(
                container.variables(filter, name_format, value_format, start, count)
            )
        }

    def evaluate_request(self, request: Request):
        format = self._parse_value_format(request)
        expr = request("expression", str)
        frame_id = request("frameId", int)
        frame = StackFrame.get(frame_id)
        if frame is None:
            return request.isnt_valid(f'Invalid "frameId": {frame_id}', silent=True)
        try:
            result = frame.evaluate(expr)
        except BaseException as exc:
            result = exc
        return eval.Result(frame, result, format)

    def setVariable_request(self, request: Request):
        format = self._parse_value_format(request)
        name = request("name", str)
        value = request("value", str)
        container_id = request("variablesReference", int)
        container = eval.VariableContainer.get(container_id)
        if container is None:
            raise request.isnt_valid(f'Invalid "variablesReference": {container_id}')
        try:
            return container.set_variable(name, value, format)
        except BaseException as exc:
            raise request.cant_handle(str(exc))

    def setExpression_request(self, request: Request):
        expr = request("expression", str)
        value = request("value", str)
        frame_id = request("frameId", int)
        frame = StackFrame.get(frame_id)
        if frame is None:
            return request.isnt_valid(f'Invalid "frameId": {frame_id}', silent=True)
        try:
            frame.evaluate(f"{expr} = ({value})", "exec")
            result = frame.evaluate(expr)
        except BaseException as exc:
            raise request.cant_handle(str(exc))
        return eval.Result(frame, result, format)

    def disconnect_request(self, request: Request):
        Breakpoint.clear()
        self._tracer.abandon_step()
        self._tracer.resume()
        return {}

    def terminate_request(self, request: Request):
        Breakpoint.clear()
        self._tracer.abandon_step()
        self._tracer.resume()
        return {}

    def disconnect(self):
        self._tracer.resume()
        self.connected_event.clear()
        return {}
