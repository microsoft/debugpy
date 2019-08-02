# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import functools
import platform

import ptvsd
from ptvsd.common import json, log, messaging, singleton
from ptvsd.common.compat import unicode
from ptvsd.adapter import channels, debuggee, contract, options, state


class _Shared(singleton.ThreadSafeSingleton):
    """Global state shared between IDE and server handlers, other than contracts.
    """

    # Only attributes that are set by IDEMessages and marked as readonly before
    # connecting to the server can go in here.
    threadsafe_attrs = {"start_method", "terminate_on_disconnect"}

    start_method = None
    """Either "launch" or "attach", depending on the request used."""

    terminate_on_disconnect = True
    """Whether the debuggee process should be terminated on disconnect."""


class Messages(singleton.Singleton):
    # Misc helpers that are identical for both IDEMessages and ServerMessages.

    # Shortcut for the IDE channel. This one does not check for None, because in the
    # normal stdio channel scenario, the channel will never disconnect. The debugServer
    # scenario is for testing purposes only, so it's okay to crash if IDE suddenly
    # disconnects in that case.
    @property
    def _ide(self):
        return _channels.ide()

    @property
    def _server(self):
        """Raises MessageHandingError if the server is not available.

        To test whether it is available or not, use _channels.server() instead,
        following the guidelines in its docstring.
        """
        server = _channels.server()
        if server is None:
            messaging.Message.isnt_valid(
                "Connection to debug server is not established yet"
            )
        return server

    # Specifies the allowed adapter states for a message handler - if the corresponding
    # message is received in a state that is not listed, the handler is not invoked.
    # If the message is a request, a failed response is returned.
    @staticmethod
    def _only_allowed_while(*states):
        def decorate(handler):
            @functools.wraps(handler)
            def handle_if_allowed(self, message):
                current_state = state.current()
                if current_state in states:
                    return handler(self, message)
                if isinstance(message, messaging.Request):
                    message.isnt_valid(
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

    # Until the server message loop is, this isn't really shared, so we can simplify
    # synchronization by keeping it exclusive until then. This way, all attributes
    # that are computed during initialization and never change after don't need to be
    # synchronized at all.
    _shared = _Shared(shared=False)

    # Until "launch" or "attach", there's no debug server yet, and so we can't propagate
    # messages. But they will need to be replayed once we establish connection to server,
    # so store them here until then. After all messages are replayed, it is set to None.
    _initial_messages = []

    # A decorator to add the message to initial_messages if needed before handling it.
    # Must be applied to the handler for every message that can be received before
    # connection to the debug server can be established while handling attach/launch,
    # and that must be replayed to the server once it is established.
    def _replay_to_server(handler):
        @functools.wraps(handler)
        def store_and_handle(self, message):
            if self._initial_messages is not None:
                self._initial_messages.append(message)
            return handler(self, message)

        return store_and_handle

    # Generic event handler. There are no specific handlers for IDE events, because
    # there are no events from the IDE in DAP - but we propagate them if we can, in
    # case some events appear in future protocol versions.
    @_replay_to_server
    def event(self, event):
        server = _channels.server()
        if server is not None:
            server.propagate(event)

    # Generic request handler, used if there's no specific handler below.
    def request(self, request):
        return self._server.delegate(request)

    @_replay_to_server
    @_only_allowed_while("starting")
    def initialize_request(self, request):
        contract.ide.parse(request)
        state.change("initializing")
        return self._INITIALIZE_RESULT

    # Handles various attributes common to both "launch" and "attach".
    def _debug_config(self, request):
        assert request.command in ("launch", "attach")
        self._shared.start_method = request.command
        _Shared.readonly_attrs.add("start_method")

        # We're about to connect to the server and start the message loop for its
        # handlers, so _shared is actually going to be shared from now on.
        self._shared.share()

        # TODO: handle "logToFile". Maybe also "trace" (to Debug Output) like Node.js?
        pass

    @_replay_to_server
    @_only_allowed_while("initializing")
    def launch_request(self, request):
        self._debug_config(request)

        # TODO: nodebug
        debuggee.spawn_and_connect(request)

        return self._configure(request)

    @_replay_to_server
    @_only_allowed_while("initializing")
    def attach_request(self, request):
        self._shared.terminate_on_disconnect = False
        _Shared.readonly_attrs.add("terminate_on_disconnect")
        self._debug_config(request)

        options.host = request.arguments.get("host", options.host)
        options.port = int(request.arguments.get("port", options.port))
        _channels.connect_to_server(address=(options.host, options.port))

        return self._configure(request)

    def _set_debugger_properties(self, request):
        debug_options = set(request("debugOptions", json.array(unicode)))
        client_os_type = None
        if 'WindowsClient' in debug_options or 'WINDOWS' in debug_options:
            client_os_type = 'WINDOWS'
        elif 'UnixClient' in debug_options or 'UNIX' in debug_options:
            client_os_type = 'UNIX'
        else:
            client_os_type = 'WINDOWS' if platform.system() == 'Windows' else 'UNIX'

        try:
            self._server.request("setDebuggerProperty", arguments={
                "dontTraceStartPatterns": ["\\ptvsd\\", "/ptvsd/"],
                "dontTraceEndPatterns": ["ptvsd_launcher.py"],
                "skipSuspendOnBreakpointException": ("BaseException",),
                "skipPrintBreakpointException": ("NameError",),
                "multiThreadsSingleNotification": True,
                "ideOS": client_os_type,
            })
        except messaging.MessageHandlingError as exc:
            exc.propagate(request)

    # Handles the configuration request sequence for "launch" or "attach", from when
    # the "initialized" event is sent, to when "configurationDone" is received; see
    # https://github.com/microsoft/vscode/issues/4902#issuecomment-368583522
    def _configure(self, request):
        log.debug("Replaying previously received messages to server.")

        assert len(self._initial_messages)
        initialize = self._initial_messages.pop(0)
        assert initialize.is_request("initialize")

        # We want to make sure that no other server message handler can execute until
        # we receive and parse the response to "initialize", to avoid race conditions
        # with those handlers accessing contract.server. Thus, we send the request and
        # register the callback first, and only then start the server message loop.
        server_initialize = self._server.propagate(initialize)
        server_initialize.on_response(lambda response: contract.server.parse(response))
        self._server.start()
        server_initialize.wait_for_response()

        for msg in self._initial_messages:
            # TODO: validate server response to ensure it matches our own earlier.
            self._server.propagate(msg)

        log.debug("Finished replaying messages to server.")
        self.initial_messages = None

        self._set_debugger_properties(request)

        # Let the IDE know that it can begin configuring the adapter.
        state.change("configuring")
        self._ide.send_event("initialized")

        # Process further incoming messages, until we get "configurationDone".
        while state.current() == "configuring":
            yield

    @_only_allowed_while("configuring")
    def configurationDone_request(self, request):
        ret = self._server.delegate(request)
        state.change("running")
        ServerMessages().release_events()
        return ret

    def _disconnect_or_terminate_request(self, request):
        assert request.is_request("disconnect") or request.is_request("terminate")

        if request("restart", json.default(False)):
            request.isnt_valid("Restart is not supported")

        terminate = (request.command == "terminate") or request(
            "terminateDebuggee", json.default(self._shared.terminate_on_disconnect)
        )

        server = _channels.server()
        server_exc = None
        terminate_requested = False
        result = {}

        try:
            state.change("shutting_down")
        except state.InvalidStateTransition:
            # Can happen if the IDE or the server disconnect while we were handling
            # this. If it was the server, we want to move on so that we can report
            # to the IDE before exiting. If it was the IDE, disconnect() handler has
            # already dealt with the server, and there isn't anything else we can do.
            pass
        else:
            if server is not None:
                try:
                    result = server.delegate(request)
                except messaging.MessageHandlingError as exc:
                    # If the server was there, but failed to handle the request, we want
                    # to propagate that failure back to the IDE - but only after we have
                    # recorded the state transition and terminated the debuggee if needed.
                    server_exc = exc
                except Exception:
                    # The server might have already disconnected - this is not an error.
                    pass
                else:
                    terminate_requested = terminate

        if terminate:
            # If we asked the server to terminate, give it some time to do so before
            # we kill the debuggee process. Otherwise, just kill it immediately.
            debuggee.terminate(5 if terminate_requested else 0)

        if server_exc is None:
            return result
        else:
            server_exc.propagate(request)

    disconnect_request = _disconnect_or_terminate_request
    terminate_request = _disconnect_or_terminate_request

    @_only_allowed_while("running")
    def pause_request(self, request):
        request.arguments["threadId"] = "*"
        self._server.delegate(request)
        return {}

    @_only_allowed_while("running")
    def continue_request(self, request):
        request.arguments["threadId"] = "*"
        self._server.delegate(request)
        return {"allThreadsContinued": True}

    @_only_allowed_while("configuring", "running")
    def ptvsd_systemInfo_request(self, request):
        result = {"ptvsd": {"version": ptvsd.__version__}}
        server = _channels.server()
        if server is not None:
            try:
                pydevd_info = server.request("pydevdSystemInfo")
            except Exception:
                # If the server has already disconnected, or couldn't handle it,
                # report what we've got.
                pass
            else:
                result.update(pydevd_info)
        return result

    # Adapter's stdout was closed by IDE.
    def disconnect(self):
        terminate_on_disconnect = self._shared.terminate_on_disconnect
        try:
            try:
                state.change("shutting_down")
            except state.InvalidStateTransition:
                # Either we have already received "disconnect" or "terminate" from the
                # IDE and delegated it to the server, or the server dropped connection.
                # Either way, everything that needed to be done is already done.
                return
            else:
                # Can happen if the IDE was force-closed or crashed.
                log.warning(
                    'IDE disconnected without sending "disconnect" or "terminate".'
                )

            server = _channels.server()
            if server is None:
                if terminate_on_disconnect:
                    # It happened before we connected to the server, so we cannot gracefully
                    # terminate the debuggee. Force-kill it immediately.
                    debuggee.terminate()
                return

            # Try to shut down the server gracefully, even though the adapter wasn't.
            command = "terminate" if terminate_on_disconnect else "disconnect"
            try:
                server.send_request(command)
            except Exception:
                # The server might have already disconnected as well, or it might fail
                # to handle the request. But we can't report failure to the IDE at this
                # point, and it's already logged, so just move on.
                pass

        finally:
            if terminate_on_disconnect:
                # If debuggee is still there, give it some time to terminate itself,
                # then force-kill. Since the IDE is gone already, and nobody is waiting
                # for us to respond, there's no rush.
                debuggee.terminate(after=60)


class ServerMessages(Messages):
    """Message handlers and the associated global state for the server channel.
    """

    _only_allowed_while = Messages._only_allowed_while

    _shared = _Shared()
    _saved_messages = []
    _hold_messages = True

    # Generic request handler, used if there's no specific handler below.
    def request(self, request):
        # Do not delegate requests from the server by default. There is a security
        # boundary between the server and the adapter, and we cannot trust arbitrary
        # requests sent over that boundary, since they may contain arbitrary code
        # that the IDE will execute - e.g. "runInTerminal". The adapter must only
        # propagate requests that it knows are safe.
        request.isnt_valid("Requests from the debug server to the IDE are not allowed.")

    # Generic event handler, used if there's no specific handler below.
    def event(self, event):
        # NOTE: This is temporary until debug server is updated to follow
        # DAP spec so we don't receive debugger events before configuration
        # done is finished.
        with self._lock:
            if self._hold_messages:
                self._saved_messages.append(event)
            else:
                self._ide.propagate(event)

    def initialized_event(self, event):
        # NOTE: This should be suppressed from server, if we want to remove
        # this then we should ensure that debug server follows DAP spec and
        # also remove the 'initialized' event sent from IDE messages.
        pass

    @_only_allowed_while("running")
    def ptvsd_subprocess_event(self, event):
        sub_pid = event("processId", int)
        try:
            debuggee.register_subprocess(sub_pid)
        except Exception as exc:
            event.cant_handle("{0}", exc)
        self._ide.propagate(event)

    def terminated_event(self, event):
        # Do not propagate this, since we'll report our own.
        pass

    @_only_allowed_while("running")
    def exited_event(self, event):
        # For "launch", the adapter will report the event itself by observing the
        # debuggee process directly, allowing the exit code to be captured more
        # accurately. Thus, there's no need to propagate it in that case.
        if self._shared.start_method == "attach":
            self._ide.propagate(event)

    # Socket was closed by the server.
    def disconnect(self):
        log.info("Debug server disconnected.")
        _channels.close_server()

        # In "launch", we must always report "exited", since we did not propagate it
        # when the server reported it. In "attach", if the server disconnected without
        # reporting "exited", we have no way to retrieve the exit code of the remote
        # debuggee process - indeed, we don't even know if it exited or not.
        report_exit = self._shared.start_method == "launch"

        try:
            state.change("shutting_down")
        except state.InvalidStateTransition:
            # The IDE has either disconnected already, or requested "disconnect".
            # There's no point reporting "exited" anymore.
            report_exit = False

        if report_exit:
            # The debuggee process should exit shortly after it has disconnected, but just
            # in case it gets stuck, don't wait forever, and force-kill it if needed.
            debuggee.terminate(after=5)
            self._ide.send_event("exited", {"exitCode": debuggee.exit_code})

        self._ide.send_event("terminated")

    def release_events(self):
        # NOTE: This is temporary until debug server is updated to follow
        # DAP spec so we don't receive debugger events before configuration
        # done is finished.
        with self._lock:
            self._hold_messages = False
            for e in self._saved_messages:
                self._ide.propagate(e)


_channels = channels.Channels()
