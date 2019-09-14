# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import platform

import ptvsd
from ptvsd.common import json, log, messaging
from ptvsd.common.compat import unicode
from ptvsd.adapter import components


class IDE(components.Component):
    """Handles the IDE side of a debug session."""

    message_handler = components.Component.message_handler

    class Capabilities(components.Capabilities):
        PROPERTIES = {
            "supportsVariableType": False,
            "supportsVariablePaging": False,
            "supportsRunInTerminalRequest": False,
            "supportsMemoryReferences": False,
        }

    class Expectations(components.Capabilities):
        PROPERTIES = {
            "locale": "en-US",
            "linesStartAt1": True,
            "columnsStartAt1": True,
            "pathFormat": json.enum("path"),  # we don't support "uri"
        }

    def __init__(self, session, stream):
        super(IDE, self).__init__(session, stream)

        self.client_id = None
        """ID of the connecting client. This can be 'test' while running tests."""

        self._initialize_request = None
        """The "initialize" request as received from the IDE, to propagate to the
        server later."""

        self._deferred_events = []
        """Deferred events from the launcher and the server that must be propagated
        only if and when the "launch" or "attach" response is sent.
        """

        assert not session.ide
        session.ide = self

        self.channel.send_event(
            "output",
            {
                "category": "telemetry",
                "output": "ptvsd.adapter",
                "data": {"version": ptvsd.__version__},
            },
        )

    def propagate_after_start(self, event):
        # pydevd starts sending events as soon as we connect, but the IDE doesn't
        # expect to see any until it receives the response to "launch" or "attach"
        # request. If IDE is not ready yet, save the event instead of propagating
        # it immediately.
        if self._deferred_events is not None:
            self._deferred_events.append(event)
            log.debug("Propagation deferred.")
        else:
            self.ide.channel.propagate(event)

    def _propagate_deferred_events(self):
        log.debug("Propagating deferred events to {0}...", self.ide)
        for event in self._deferred_events:
            log.debug("Propagating deferred {0}", event.describe())
            self.ide.channel.propagate(event)
        log.info("All deferred events propagated to {0}.", self.ide)
        self._deferred_events = None

    # Generic event handler. There are no specific handlers for IDE events, because
    # there are no events from the IDE in DAP - but we propagate them if we can, in
    # case some events appear in future protocol versions.
    @message_handler
    def event(self, event):
        if self.server:
            self.server.channel.propagate(event)

    # Generic request handler, used if there's no specific handler below.
    @message_handler
    def request(self, request):
        return self.server.channel.delegate(request)

    @message_handler
    def initialize_request(self, request):
        if self._initialize_request is not None:
            raise request.isnt_valid("Session is already initialized")

        self.client_id = request("clientID", "")
        self.capabilities = self.Capabilities(self, request)
        self.expectations = self.Expectations(self, request)
        self._initialize_request = request

        return {
            "supportsCompletionsRequest": True,
            "supportsConditionalBreakpoints": True,
            "supportsConfigurationDoneRequest": True,
            "supportsDebuggerProperties": True,
            "supportsDelayedStackTraceLoading": True,
            "supportsEvaluateForHovers": True,
            "supportsExceptionInfoRequest": True,
            "supportsExceptionOptions": True,
            "supportsHitConditionalBreakpoints": True,
            "supportsLogPoints": True,
            "supportsModulesRequest": True,
            "supportsSetExpression": True,
            "supportsSetVariable": True,
            "supportsValueFormattingOptions": True,
            "supportsTerminateDebuggee": True,
            "supportsGotoTargetsRequest": True,
            "exceptionBreakpointFilters": [
                {"filter": "raised", "label": "Raised Exceptions", "default": False},
                {"filter": "uncaught", "label": "Uncaught Exceptions", "default": True},
            ],
        }

    # Common code for "launch" and "attach" request handlers.
    #
    # See https://github.com/microsoft/vscode/issues/4902#issuecomment-368583522
    # for the sequence of request and events necessary to orchestrate the start.
    def _start_message_handler(f):
        f = components.Component.message_handler(f)

        def handle(self, request):
            assert request.is_request("launch", "attach")
            if self._initialize_request is None:
                raise request.isnt_valid("Session is not initialized yet")
            if self.launcher:
                raise request.isnt_valid("Session is already started")

            self.session.no_debug = request("noDebug", json.default(False))
            self.session.debug_options = set(
                request("debugOptions", json.array(unicode))
            )

            f(self, request)

            if self.server:
                self.server.initialize(self._initialize_request)
                self._initialize_request = None

                # pydevd doesn't send "initialized", and responds to the start request
                # immediately, without waiting for "configurationDone". If it changes
                # to conform to the DAP spec, we'll need to defer waiting for response.
                self.server.channel.delegate(request)

            if self.session.no_debug:
                request.respond({})
                self._propagate_deferred_events()
                return

            if {"WindowsClient", "Windows"} & self.session.debug_options:
                client_os_type = "WINDOWS"
            elif {"UnixClient", "UNIX"} & self.session.debug_options:
                client_os_type = "UNIX"
            else:
                client_os_type = "WINDOWS" if platform.system() == "Windows" else "UNIX"
            self.server.channel.request(
                "setDebuggerProperty",
                {
                    "skipSuspendOnBreakpointException": ("BaseException",),
                    "skipPrintBreakpointException": ("NameError",),
                    "multiThreadsSingleNotification": True,
                    "ideOS": client_os_type,
                },
            )

            # Let the IDE know that it can begin configuring the adapter.
            self.channel.send_event("initialized")

            self._start_request = request
            return messaging.NO_RESPONSE  # will respond on "configurationDone"

        return handle

    @_start_message_handler
    def launch_request(self, request):
        sudo = request("sudo", json.default("Sudo" in self.session.debug_options))
        if sudo:
            if platform.system() == "Windows":
                raise request.cant_handle('"sudo":true is not supported on Windows.')
        else:
            if "Sudo" in self.session.debug_options:
                raise request.isnt_valid(
                    '"sudo":false and "debugOptions":["Sudo"] are mutually exclusive'
                )

        # Launcher doesn't use the command line at all, but we pass the arguments so
        # that they show up in the terminal if we're using "runInTerminal".
        if "program" in request:
            args = request("program", json.array(unicode, vectorize=True, size=(1,)))
        elif "module" in request:
            args = ["-m"] + request(
                "module", json.array(unicode, vectorize=True, size=(1,))
            )
        elif "code" in request:
            args = ["-c"] + request(
                "code", json.array(unicode, vectorize=True, size=(1,))
            )
        else:
            args = []
        args += request("args", json.array(unicode))

        console = request(
            "console",
            json.enum(
                "internalConsole",
                "integratedTerminal",
                "externalTerminal",
                optional=True,
            ),
        )
        console_title = request("consoleTitle", json.default("Python Debug Console"))

        self.session.spawn_debuggee(request, sudo, args, console, console_title)

        if "RedirectOutput" in self.session.debug_options:
            # The launcher is doing output redirection, so we don't need the server.
            request.arguments["debugOptions"].remove("RedirectOutput")

    @_start_message_handler
    def attach_request(self, request):
        if self.session.no_debug:
            raise request.isnt_valid('"noDebug" is not supported for "attach"')

        pid = request("processId", int, optional=True)
        if pid == ():
            # When the adapter is spawned by the debug server, it is connected to the
            # latter from the get go, and "host" and "port" in the "attach" request
            # are actually the host and port on which the adapter itself was listening,
            # so we can ignore those.
            if self.server:
                return

            host = request("host", "127.0.0.1")
            port = request("port", int)
            if request("listen", False):
                with self.accept_connection_from_server((host, port)):
                    pass
            else:
                self.session.connect_to_server((host, port))
        else:
            if self.server:
                raise request.isnt_valid(
                    '"attach" with "processId" cannot be serviced by adapter '
                    "that is already associated with a debug server"
                )

            ptvsd_args = request("ptvsdArgs", json.array(unicode))
            self.session.inject_server(pid, ptvsd_args)

    @message_handler
    def configurationDone_request(self, request):
        if self._start_request is None:
            request.cant_handle(
                '"configurationDone" is only allowed during handling of a "launch" '
                'or an "attach" request'
            )

        try:
            request.respond(self.server.channel.delegate(request))
        finally:
            self._start_request.respond({})
            self._start_request = None
            self._propagate_deferred_events()

    @message_handler
    def pause_request(self, request):
        request.arguments["threadId"] = "*"
        return self.server.channel.delegate(request)

    @message_handler
    def continue_request(self, request):
        request.arguments["threadId"] = "*"

        try:
            return self.server.channel.delegate(request)
        except messaging.NoMoreMessages:
            # pydevd can sometimes allow the debuggee to exit before the queued
            # "continue" response gets sent. Thus, a failed "continue" response
            # indicating that the server disconnected should be treated as success.
            return {"allThreadsContinued": True}

    @message_handler
    def ptvsd_systemInfo_request(self, request):
        result = {"ptvsd": {"version": ptvsd.__version__}}
        if self.server:
            try:
                pydevd_info = self.server.channel.request("pydevdSystemInfo")
            except Exception:
                # If the server has already disconnected, or couldn't handle it,
                # report what we've got.
                pass
            else:
                result.update(pydevd_info)
        return result

    @message_handler
    def terminate_request(self, request):
        self.session.finalize('IDE requested "terminate"', terminate_debuggee=True)
        return {}

    @message_handler
    def disconnect_request(self, request):
        self.session.finalize(
            'IDE requested "disconnect"',
            request("terminateDebuggee", json.default(bool(self.launcher))),
        )
        return {}
