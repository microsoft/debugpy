# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

from ptvsd.adapter import components


class Server(components.Component):
    """Handles the debug server side of a debug session."""

    message_handler = components.Component.message_handler

    class Capabilities(components.Capabilities):
        PROPERTIES = {
            "supportsCompletionsRequest": False,
            "supportsConditionalBreakpoints": False,
            "supportsConfigurationDoneRequest": False,
            "supportsDataBreakpoints": False,
            "supportsDelayedStackTraceLoading": False,
            "supportsDisassembleRequest": False,
            "supportsEvaluateForHovers": False,
            "supportsExceptionInfoRequest": False,
            "supportsExceptionOptions": False,
            "supportsFunctionBreakpoints": False,
            "supportsGotoTargetsRequest": False,
            "supportsHitConditionalBreakpoints": False,
            "supportsLoadedSourcesRequest": False,
            "supportsLogPoints": False,
            "supportsModulesRequest": False,
            "supportsReadMemoryRequest": False,
            "supportsRestartFrame": False,
            "supportsRestartRequest": False,
            "supportsSetExpression": False,
            "supportsSetVariable": False,
            "supportsStepBack": False,
            "supportsStepInTargetsRequest": False,
            "supportsTerminateDebuggee": False,
            "supportsTerminateRequest": False,
            "supportsTerminateThreadsRequest": False,
            "supportsValueFormattingOptions": False,
            "exceptionBreakpointFilters": [],
            "additionalModuleColumns": [],
            "supportedChecksumAlgorithms": [],
        }

    def __init__(self, session, stream):
        super(Server, self).__init__(session, stream)

        self.pid = None
        """Process ID of the debuggee process, as reported by the server."""

        assert not session.server
        session.server = self

    def initialize(self, request):
        assert request.is_request("initialize")
        request = self.channel.propagate(request)
        request.wait_for_response()
        self.capabilities = self.Capabilities(self, request.response)

    def set_debugger_property(self, arguments):
        assert isinstance(arguments, dict)
        self.channel.request("setDebuggerProperty", arguments=arguments)

    # Generic request handler, used if there's no specific handler below.
    @message_handler
    def request(self, request):
        # Do not delegate requests from the server by default. There is a security
        # boundary between the server and the adapter, and we cannot trust arbitrary
        # requests sent over that boundary, since they may contain arbitrary code
        # that the IDE will execute - e.g. "runInTerminal". The adapter must only
        # propagate requests that it knows are safe.
        raise request.isnt_valid(
            "Requests from the debug server to the IDE are not allowed."
        )

    # Generic event handler, used if there's no specific handler below.
    @message_handler
    def event(self, event):
        self.ide.propagate_after_start(event)

    @message_handler
    def initialized_event(self, event):
        # pydevd doesn't send it, but the adapter will send its own in any case.
        pass

    @message_handler
    def process_event(self, event):
        self.pid = event("systemProcessId", int)

        if self.launcher:
            assert self.session.pid is not None
        else:
            assert self.session.pid is None
        if self.session.pid is not None and self.session.pid != self.pid:
            event.cant_handle(
                '"process" event mismatch: launcher reported "systemProcessId":{0}, '
                'but server reported "systemProcessId":{1}',
                self.session.pid,
                self.pid,
            )
        else:
            self.session.pid = self.pid

        # If there is a launcher, it's handling the process event.
        if not self.launcher:
            self.ide.propagate_after_start(event)

    @message_handler
    def continued_event(self, event):
        # https://github.com/microsoft/ptvsd/issues/1530
        #
        # DAP specification says that a step request implies that only the thread on
        # which that step occurred is resumed for the duration of the step. However,
        # for VS compatibility, pydevd can operate in a mode that resumes all threads
        # instead. This is set according to the value of "steppingResumesAllThreads"
        # in "launch" or "attach" request, which defaults to true. If explicitly set
        # to false, pydevd will only resume the thread that was stepping.
        #
        # To ensure that the IDE is aware that other threads are getting resumed in
        # that mode, pydevd sends a "continued" event with "allThreadsResumed": true.
        # when responding to a step request. This ensures correct behavior in VSCode
        # and other DAP-conformant clients.
        #
        # On the other hand, VS does not follow the DAP specification in this regard.
        # When it requests a step, it assumes that all threads will be resumed, and
        # does not expect to see "continued" events explicitly reflecting that fact.
        # If such events are sent regardless, VS behaves erratically. Thus, we have
        # to suppress them specifically for VS.
        if self.ide.client_id not in ("visualstudio", "vsformac"):
            self.ide.propagate_after_start(event)

    @message_handler
    def exited_event(self, event):
        # If there is a launcher, it's handling the exit code.
        if not self.launcher:
            self.ide.propagate_after_start(event)

    @message_handler
    def terminated_event(self, event):
        # Do not propagate this, since we'll report our own.
        pass
