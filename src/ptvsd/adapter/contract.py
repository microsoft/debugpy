# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

"""Runtime contracts for the IDE and the server.
"""

from ptvsd.common import fmt, json, log, singleton


class Capabilities(dict):
    """A collection of feature flags. Corresponds to JSON properties in the DAP
    "initialize" request, other than those that identify the party.
    """

    PROPERTIES = {}
    """JSON property names and default values for the the capabilities represented
    by instances of this class. Keys are names, and values are either default values
    or validators.

    If the value is callable, it must be a JSON validator; see ptvsd.common.json for
    details. If the value is not callable, it is as if json.default(value) validator
    was used instead.
    """

    def __init__(self, message):
        """Parses an "initialize" request or response and extracts the feature flags.

        For every "X" in self.PROPERTIES, sets self["X"] to the corresponding value
        from message.payload if it's present there, or to the default value otherwise.
        """

        payload = message.payload
        for name, validate in self.PROPERTIES.items():
            value = payload.get(name, ())
            if not callable(validate):
                validate = json.default(validate)

            try:
                value = validate(value)
            except Exception as exc:
                raise message.isnt_valid("{0!j} {1}", name, exc)

            assert value != (), fmt(
                "{0!j} must provide a default value for missing properties.", validate
            )
            self[name] = value

        log.debug("{0}", self)

    def __repr__(self):
        return fmt("{0}: {1!j}", type(self).__name__, dict(self))


class IDECapabilities(Capabilities):
    PROPERTIES = {
        "supportsVariableType": False,
        "supportsVariablePaging": False,
        "supportsRunInTerminalRequest": False,
        "supportsMemoryReferences": False,
    }


class ServerCapabilities(Capabilities):
    PROPERTIES = {
        "supportsConfigurationDoneRequest": False,
        "supportsFunctionBreakpoints": False,
        "supportsConditionalBreakpoints": False,
        "supportsHitConditionalBreakpoints": False,
        "supportsEvaluateForHovers": False,
        "supportsStepBack": False,
        "supportsSetVariable": False,
        "supportsRestartFrame": False,
        "supportsGotoTargetsRequest": False,
        "supportsStepInTargetsRequest": False,
        "supportsCompletionsRequest": False,
        "supportsModulesRequest": False,
        "supportsRestartRequest": False,
        "supportsExceptionOptions": False,
        "supportsValueFormattingOptions": False,
        "supportsExceptionInfoRequest": False,
        "supportTerminateDebuggee": False,
        "supportsDelayedStackTraceLoading": False,
        "supportsLoadedSourcesRequest": False,
        "supportsLogPoints": False,
        "supportsTerminateThreadsRequest": False,
        "supportsSetExpression": False,
        "supportsTerminateRequest": False,
        "supportsDataBreakpoints": False,
        "supportsReadMemoryRequest": False,
        "supportsDisassembleRequest": False,
        "exceptionBreakpointFilters": [],
        "additionalModuleColumns": [],
        "supportedChecksumAlgorithms": [],
    }


class IDEExpectations(Capabilities):
    PROPERTIES = {
        "locale": "en-US",
        "linesStartAt1": True,
        "columnsStartAt1": True,
        "pathFormat": json.enum("path"),  # we don't support "uri"
    }


# Contracts don't have to be thread-safe. The reason is that both contracts are parsed
# while handling IDE messages, so the IDE message loop doesn't need to synchronize;
# and on the other hand, the server message loop is not started until the contracts
# are parsed, and thus cannot observe any changes.


class IDEContract(singleton.Singleton):
    """The contract for the IDE side. Identifies the IDE client, and describes its
    capabilities, and expectations from the adapter.
    """

    clientID = None
    capabilities = None
    expectations = None

    def parse(self, message):
        assert self.capabilities is None and self.expectations is None
        assert message.is_request("initialize")

        self.client_id = message.arguments.get("clientID", "")
        self.capabilities = IDECapabilities(message)
        self.expectations = IDEExpectations(message)


class ServerContract(singleton.Singleton):
    """The contract for the server side. Describes its capabilities.
    """

    capabilities = None

    def parse(self, message):
        assert self.capabilities is None
        assert message.is_response("initialize")

        self.capabilities = ServerCapabilities(message)


ide = IDEContract()
server = ServerContract()
