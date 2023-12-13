# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import os
import sys
import threading
from itertools import islice

from debugpy.adapter import components
from debugpy.common import json, log, messaging, sockets
from debugpy.common.messaging import Request
from debugpy.server import tracing, eval
from debugpy.server.tracing import Breakpoint, StackFrame


class Adapter:
    """Represents the debug adapter connected to this debug server."""

    class Capabilities(components.Capabilities):
        PROPERTIES = {
            "supportsVariableType": False,
            "supportsVariablePaging": False,
            "supportsRunInTerminalRequest": False,
            "supportsMemoryReferences": False,
            "supportsArgsCanBeInterpretedByShell": False,
            "supportsStartDebuggingRequest": False,
        }

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

    def __init__(self, stream: messaging.JsonIOStream):
        self._is_initialized = False
        self._has_started = False
        self._client_id = None
        self._capabilities = None
        self._expectations = None
        self._start_request = None

        self.channel = messaging.JsonMessageChannel(stream, self)
        self.channel.start()

    @classmethod
    def connect(self, host, port):
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

        exception_breakpoint_filters = [
            {
                "filter": "raised",
                "label": "Raised Exceptions",
                "default": False,
                "description": "Break whenever any exception is raised.",
            },
            {
                "filter": "uncaught",
                "label": "Uncaught Exceptions",
                "default": True,
                "description": "Break when the process is exiting due to unhandled exception.",
            },
            {
                "filter": "userUnhandled",
                "label": "User Uncaught Exceptions",
                "default": False,
                "description": "Break when exception escapes into library code.",
            },
        ]

        return {
            "supportsCompletionsRequest": True,
            "supportsConditionalBreakpoints": True,
            "supportsConfigurationDoneRequest": True,
            "supportsDebuggerProperties": True,
            "supportsDelayedStackTraceLoading": True,
            "supportsEvaluateForHovers": True,
            "supportsExceptionInfoRequest": True,
            "supportsExceptionOptions": True,
            "supportsFunctionBreakpoints": True,
            "supportsHitConditionalBreakpoints": True,
            "supportsLogPoints": True,
            "supportsModulesRequest": True,
            "supportsSetExpression": True,
            "supportsSetVariable": True,
            "supportsValueFormattingOptions": True,
            "supportsTerminateRequest": True,
            "supportsGotoTargetsRequest": True,
            "supportsClipboardContext": True,
            "exceptionBreakpointFilters": exception_breakpoint_filters,
            "supportsStepInTargetsRequest": True,
        }

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
            request.cant_handle(
                '"configurationDone" is only allowed during handling of a "launch" '
                'or an "attach" request'
            )

        tracing.start()
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
        # TODO
        return Exception("Exception breakpoints are not supported")

    def setBreakpoints_request(self, request: Request):
        # TODO: implement source.reference for setting breakpoints in sources for
        # which source code was decompiled or retrieved via inspect.getsource.
        source = request("source", json.object())
        path = source("path", str)

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
            bps = [{"line": line} for line in lines]

        Breakpoint.clear([path])
        bps_set = [Breakpoint.set(path, bp["line"]) for bp in bps]
        return {"breakpoints": bps_set}

    def threads_request(self, request: Request):
        return {"threads": tracing.Thread.enumerate()}

    def stackTrace_request(self, request: Request):
        thread_id = request("threadId", int)
        start_frame = request("startFrame", 0)

        thread = tracing.Thread.get(thread_id)
        if thread is None:
            raise request.isnt_valid(f'Invalid "threadId": {thread_id}')

        frames = None
        try:
            frames = (
                frame for frame in thread.stack_trace() if not frame.is_internal()
            )
            frames = islice(frames, start_frame, None)
            return {"stackFrames": list(frames)}
        finally:
            del frames

    def pause_request(self, request: Request):
        if request.arguments.get("threadId", None) == "*":
            thread_ids = None
        else:
            thread_ids = [request("threadId", int)]
        tracing.pause(thread_ids)
        return {}

    def continue_request(self, request: Request):
        if request.arguments.get("threadId", None) == "*":
            thread_ids = None
        else:
            thread_ids = [request("threadId", int)]
        single_thread = request("singleThread", False)
        tracing.resume(thread_ids if single_thread else None)
        return {}

    def stepIn_request(self, request: Request):
        # TODO: support "singleThread" and "granularity"
        thread_id = request("threadId", int)
        tracing.step_in(thread_id)
        return {}

    def stepOut_request(self, request: Request):
        # TODO: support "singleThread" and "granularity"
        thread_id = request("threadId", int)
        tracing.step_out(thread_id)
        return {}

    def next_request(self, request: Request):
        # TODO: support "singleThread" and "granularity"
        thread_id = request("threadId", int)
        tracing.step_over(thread_id)
        return {}

    def scopes_request(self, request: Request):
        frame_id = request("frameId", int)
        frame = StackFrame.get(frame_id)
        if frame is None:
            request.isnt_valid(f'Invalid "frameId": {frame_id}')
        return {"scopes": frame.scopes()}

    def variables_request(self, request: Request):
        container_id = request("variablesReference", int)
        container = eval.VariableContainer.get(container_id)
        if container is None:
            raise request.isnt_valid(f'Invalid "variablesReference": {container_id}')
        return {"variables": list(container.variables())}

    def evaluate_request(self, request: Request):
        expr = request("expression", str)
        frameId = request("frameId", int)
        var = eval.evaluate(expr, frameId)
        return {"result": var.repr, "variablesReference": var.id}

    def disconnect_request(self, request: Request):
        tracing.Breakpoint.clear()
        tracing.abandon_step()
        tracing.resume()
        return {}

    def terminate_request(self, request: Request):
        tracing.Breakpoint.clear()
        tracing.abandon_step()
        tracing.resume()
        return {}

    def disconnect(self):
        tracing.resume()
        self.connected_event.clear()
        return {}
