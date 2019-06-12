# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals


from ptvsd.common import log, messaging, singleton
from ptvsd.adapter import channels, debuggee, state


class Shared(singleton.ThreadSafeSingleton):
    """Global state shared between IDE and server handlers."""

    client_id = ""  # always a string to avoid None checks


class Messages(singleton.Singleton):
    # Misc helpers that are identical for both IDEMessages and ServerMessages.

    _channels = channels.Channels()

    @property
    def _ide(self):
        return self._channels.ide

    @property
    def _server(self):
        """Raises RequestFailure if the server is not available.

        To test whether it is available or not, use _channels.server instead, and
        check for None.
        """

        server = self._channels.server
        if server is None:
            messaging.raise_failure("Connection to debug server is not established yet")
        return server

    # Specifies the allowed adapter states for a message handler - if the corresponding
    # message is received in a state that is not listed, the handler is not invoked.
    # If the message is a request, a failed response is returned.
    def _only_allowed_while(*states):
        def decorate(handler):
            def handle_if_allowed(self, message):
                current_state = state.current()
                if current_state in states:
                    return handler(self, message)
                if isinstance(message, messaging.Request):
                    messaging.raise_failure(
                        "Request {0!r} is not allowed in adapter state {1!r}.",
                        message.command,
                        current_state,
                    )

            return handle_if_allowed

        return decorate


class IDEMessages(Messages):
    """Message handlers and the associated global state for the IDE channel.
    """

    _only_allowed_while = Messages._only_allowed_while

    # The contents of the "initialize" response that is sent from the adapter to the IDE,
    # and is expected to match what the debug server sends to the adapter once connected.
    _INITIALIZE_RESULT = {
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
        "supportTerminateDebuggee": True,
        "supportsGotoTargetsRequest": True,
        "exceptionBreakpointFilters": [
            {"filter": "raised", "label": "Raised Exceptions", "default": False},
            {"filter": "uncaught", "label": "Uncaught Exceptions", "default": True},
        ],
    }

    # Until "launch" or "attach", there's no _channels.server, and so we can't propagate
    # messages. But they will need to be replayed once we establish connection to server,
    # so store them here until then. After all messages are replayed, it is set to None.
    _initial_messages = []

    terminate_on_disconnect = True

    # A decorator to add the message to initial_messages if needed before handling it.
    # Must be applied to the handler for every message that can be received before
    # connection to the debug server can be established while handling attach/launch,
    # and that must be replayed to the server once it is established.
    def _replay_to_server(handler):
        def store_and_handle(self, message):
            if self.initial_messages is not None:
                self.initial_messages.append(message)
            return handler(self, message)

        return store_and_handle

    # Generic event handler. There are no specific handlers for IDE events, because
    # there are no events from the IDE in DAP - but we propagate them if we can, in
    # case some events appear in future protocol versions.
    @_replay_to_server
    def event(self, event):
        if self._server is not None:
            self._server.propagate(event)

    # Generic request handler, used if there's no specific handler below.
    @_replay_to_server
    def request(self, request):
        return self._server.delegate(request)

    @_replay_to_server
    @_only_allowed_while("starting")
    def initialize_request(self, request):
        with Shared() as shared:
            shared.client_id = str(request.arguments.get("clientID", ""))
        state.change("initializing")
        return self._INITIALIZE_RESULT

    # Handles various attributes common to both "launch" and "attach".
    def _debug_config(self, request):
        assert request.command in ("launch", "attach")
        pass  # TODO: options and debugOptions
        pass  # TODO: pathMappings (unless server does that entirely?)

    @_replay_to_server
    @_only_allowed_while("initializing")
    def launch_request(self, request):
        self._debug_config(request)

        # TODO: nodebug
        debuggee.launch_and_connect(request)

        return self._configure()

    @_replay_to_server
    @_only_allowed_while("initializing")
    def attach_request(self, request):
        self.terminate_on_disconnect = False
        self._debug_config(request)

        # TODO: get address and port
        channels.connect_to_server()

        return self._configure()

    # Handles the configuration request sequence for "launch" or "attach", from when
    # the "initialized" event is sent, to when "configurationDone" is received; see
    # https://github.com/microsoft/vscode/issues/4902#issuecomment-368583522
    def _configure(self):
        log.debug("Replaying previously received messages to server.")

        for msg in self.initial_messages:
            # TODO: validate server response to ensure it matches our own earlier.
            self._server.propagate(msg)

        log.debug("Finished replaying messages to server.")
        self.initial_messages = None

        # Let the IDE know that it can begin configuring the adapter.
        state.change("configuring")
        self._ide.send_event("initialized")

        # Process further incoming messages, until we get "configurationDone".
        while state.current() == "configuring":
            yield

    @_only_allowed_while("configuring")
    def configurationDone_request(self, request):
        state.change("running")
        return self._server.delegate(request)

    # Handle a "disconnect" or a "terminate" request.
    def _shutdown(self, request, terminate):
        if request.arguments.get("restart", False):
            messaging.raise_failure("Restart is not supported")

        result = self._server.delegate(request)
        state.change("shutting_down")

        if terminate:
            debuggee.terminate()

        return result

    @_only_allowed_while("running")
    def disconnect_request(self, request):
        # We've already decided earlier based on whether it was launch or attach, but
        # let the request override that.
        terminate = request.arguments.get(
            "terminateDebuggee", self.terminate_on_disconnect
        )
        return self._shutdown(request, terminate)

    @_only_allowed_while("running")
    def terminate_request(self, request):
        return self._shutdown(request, terminate=True)

    # Adapter's stdout was closed by IDE.
    def disconnect(self):
        try:
            if state.current() == "shutting_down":
                # Graceful disconnect. We have already received "disconnect" or
                # "terminate", and delegated it to the server. Nothing to do.
                return

            # Can happen if the IDE was force-closed or crashed.
            log.warn('IDE disconnected without sending "disconnect" or "terminate".')
            state.change("shutting_down")

            if self._server is None:
                if self.terminate_on_disconnect:
                    # It happened before we connected to the server, so we cannot gracefully
                    # terminate the debuggee. Force-kill it immediately.
                    debuggee.terminate()
                return

            # Try to shut down the server gracefully, even though the adapter wasn't.
            command = "terminate" if self.terminate_on_disconnect else "disconnect"
            try:
                self._server.send_request(command)
            except Exception:
                # The server might have already disconnected as well, or it might fail
                # to handle the request. But we can't report failure to the IDE at this
                # point, and it's already logged, so just move on.
                pass

        finally:
            if self.terminate_on_disconnect:
                # If debuggee is still there, give it some time to terminate itself,
                # then force-kill. Since the IDE is gone already, and nobody is waiting
                # for us to respond, there's no rush.
                debuggee.terminate(after=60)


class ServerMessages(Messages):
    """Message handlers and the associated global state for the server channel.
    """

    _channels = channels.Channels()

    # Socket was closed by the server.
    def disconnect(self):
        log.info("Debug server disconnected")

    # Generic request handler, used if there's no specific handler below.
    def request(self, request):
        return self._ide.delegate(request)

    # Generic event handler, used if there's no specific handler below.
    def event(self, event):
        self._ide.propagate(event)
