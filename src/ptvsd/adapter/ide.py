# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, division, print_function, unicode_literals

import os
import sys

import ptvsd
from ptvsd.common import fmt, json, log, messaging, sockets
from ptvsd.common.compat import unicode
from ptvsd.adapter import components, servers, sessions


class IDE(components.Component, sockets.ClientConnection):
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

    def __init__(self, sock):
        if sock == "stdio":
            log.info("Connecting to IDE over stdio...", self)
            stream = messaging.JsonIOStream.from_stdio()
            # Make sure that nothing else tries to interfere with the stdio streams
            # that are going to be used for DAP communication from now on.
            sys.stdout = sys.stderr
            sys.stdin = open(os.devnull, "r")
        else:
            stream = messaging.JsonIOStream.from_socket(sock)

        with sessions.Session() as session:
            super(IDE, self).__init__(session, stream)

            self.client_id = None
            """ID of the connecting client. This can be 'test' while running tests."""

            self.has_started = False
            """Whether the "launch" or "attach" request was received from the IDE, and
            fully handled.
            """

            self.start_request = None
            """The "launch" or "attach" request as received from the IDE.
            """

            self._initialize_request = None
            """The "initialize" request as received from the IDE, to propagate to the
            server later."""

            self._deferred_events = []
            """Deferred events from the launcher and the server that must be propagated
            only if and when the "launch" or "attach" response is sent.
            """

            self._known_subprocesses = set()
            """servers.Connection instances for subprocesses that this IDE has been
            made aware of.
            """

            session.ide = self
            session.register()

        self.channel.send_event(
            "output",
            {
                "category": "telemetry",
                "output": "ptvsd",
                "data": {"packageVersion": ptvsd.__version__},
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

        @components.Component.message_handler
        def handle(self, request):
            assert request.is_request("launch", "attach")
            if self._initialize_request is None:
                raise request.isnt_valid("Session is not initialized yet")
            if self.launcher or self.server:
                raise request.isnt_valid("Session is already started")

            self.session.no_debug = request("noDebug", json.default(False))
            if self.session.no_debug:
                servers.dont_wait_for_first_connection()

            self.session.debug_options = debug_options = set(
                request("debugOptions", json.array(unicode))
            )

            f(self, request)

            if self.server:
                self.server.initialize(self._initialize_request)
                self._initialize_request = None

                arguments = request.arguments
                if self.launcher:
                    if "RedirectOutput" in debug_options:
                        # The launcher is doing output redirection, so we don't need the
                        # server to do it, as well.
                        arguments = dict(arguments)
                        arguments["debugOptions"] = list(debug_options - {"RedirectOutput"})

                    if arguments.get("redirectOutput"):
                        arguments = dict(arguments)
                        del arguments["redirectOutput"]

                # pydevd doesn't send "initialized", and responds to the start request
                # immediately, without waiting for "configurationDone". If it changes
                # to conform to the DAP spec, we'll need to defer waiting for response.
                try:
                    self.server.channel.request(request.command, arguments)
                except messaging.MessageHandlingError as exc:
                    exc.propagate(request)

            if self.session.no_debug:
                self.start_request = request
                self.has_started = True
                request.respond({})
                self._propagate_deferred_events()
                return

            if {"WindowsClient", "Windows"} & debug_options:
                client_os_type = "WINDOWS"
            elif {"UnixClient", "UNIX"} & debug_options:
                client_os_type = "UNIX"
            else:
                client_os_type = "WINDOWS" if sys.platform == "win32" else "UNIX"
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

            self.start_request = request
            return messaging.NO_RESPONSE  # will respond on "configurationDone"

        return handle

    @_start_message_handler
    def launch_request(self, request):
        from ptvsd.adapter import launchers

        if self.session.id != 1 or len(servers.connections()):
            raise request.cant_handle('"attach" expected')

        sudo = request("sudo", json.default("Sudo" in self.session.debug_options))
        if sudo:
            if sys.platform == "win32":
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

        launchers.spawn_debuggee(
            self.session, request, sudo, args, console, console_title
        )

    @_start_message_handler
    def attach_request(self, request):
        if self.session.no_debug:
            raise request.isnt_valid('"noDebug" is not supported for "attach"')

        # There are four distinct possibilities here.
        #
        # If "processId" is specified, this is attach-by-PID. We need to inject the
        # debug server into the designated process, and then wait until it connects
        # back to us. Since the injected server can crash, there must be a timeout.
        #
        # If "subProcessId" is specified, this is attach to a known subprocess, likely
        # in response to a "ptvsd_attach" event. If so, the debug server should be
        # connected already, and thus the wait timeout is zero.
        #
        # If neither is specified, and "waitForAttach" is true, this is attach-by-socket
        # with the server expected to connect to the adapter via ptvsd.attach(). There
        # is no PID known in advance, so just wait until the first server connection
        # indefinitely, with no timeout.
        #
        # If neither is specified, and "waitForAttach" is false, this is attach-by-socket
        # in which the server has spawned the adapter via ptvsd.enable_attach(). There
        # is no PID known to the IDE in advance, but the server connection should be
        # either be there already, or the server should be connecting shortly, so there
        # must be a timeout.
        #
        # In the last two cases, if there's more than one server connection already,
        # this is a multiprocess re-attach. The IDE doesn't know the PID, so we just
        # connect it to the oldest server connection that we have - in most cases, it
        # will be the one for the root debuggee process, but if it has exited already,
        # it will be some subprocess.

        pid = request("processId", (int, unicode), optional=True)
        sub_pid = request("subProcessId", int, optional=True)
        if pid != ():
            if sub_pid != ():
                raise request.isnt_valid(
                    '"processId" and "subProcessId" are mutually exclusive'
                )
            if not isinstance(pid, int):
                try:
                    pid = int(pid)
                except Exception:
                    raise request.isnt_valid('"processId" must be parseable as int')
            ptvsd_args = request("ptvsdArgs", json.array(unicode))
            servers.inject(pid, ptvsd_args)
            timeout = 10
            pred = lambda conn: conn.pid == pid
        else:
            if sub_pid == ():
                pred = lambda conn: True
                timeout = None if request("waitForAttach", False) else 10
            else:
                pred = lambda conn: conn.pid == sub_pid
                timeout = 0

        conn = servers.wait_for_connection(self.session, pred, timeout)
        if conn is None:
            raise request.cant_handle(
                (
                    "Timed out waiting for debug server to connect."
                    if timeout
                    else "There is no debug server connected to this adapter."
                    if sub_pid == ()
                    else 'No known subprocess with "subProcessId":{0}'
                ),
                sub_pid,
            )

        try:
            conn.attach_to_session(self.session)
        except ValueError:
            request.cant_handle("{0} is already being debugged.", conn)

    @message_handler
    def configurationDone_request(self, request):
        if self.start_request is None or self.has_started:
            request.cant_handle(
                '"configurationDone" is only allowed during handling of a "launch" '
                'or an "attach" request'
            )

        try:
            self.has_started = True
            request.respond(self.server.channel.delegate(request))
        except messaging.MessageHandlingError as exc:
            self.start_request.cant_handle(str(exc))
        finally:
            self.start_request.respond({})
            self._propagate_deferred_events()

        # Notify the IDE of any child processes of the debuggee that aren't already
        # being debugged.
        for conn in servers.connections():
            if conn.server is None and conn.ppid == self.session.pid:
                self.notify_of_subprocess(conn)

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
        terminate_debuggee = request("terminateDebuggee", bool, optional=True)
        if terminate_debuggee == ():
            terminate_debuggee = None
        self.session.finalize('IDE requested "disconnect"', terminate_debuggee)
        return {}

    def notify_of_subprocess(self, conn):
        with self.session:
            if self.start_request is None or conn in self._known_subprocesses:
                return
            if "processId" in self.start_request.arguments:
                log.warning(
                    "Not reporting subprocess for {0}, because the parent process "
                    'was attached to using "processId" rather than "port".',
                    self.session,
                )
                return

            log.info("Notifying {0} about {1}.", self, conn)
            body = dict(self.start_request.arguments)
            self._known_subprocesses.add(conn)

        body["name"] = fmt("Subprocess {0}", conn.pid)
        body["request"] = "attach"
        if "host" not in body:
            body["host"] = "127.0.0.1"
        if "port" not in body:
            _, body["port"] = self.listener.getsockname()
        if "processId" in body:
            del body["processId"]
        body["subProcessId"] = conn.pid

        self.channel.send_event("ptvsd_attach", body)


listen = IDE.listen


def stop_listening():
    try:
        IDE.listener.close()
    except Exception:
        log.exception(level="warning")
