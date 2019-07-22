# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

"""Runtime contracts for the IDE and the server.
"""

from ptvsd.common import fmt, log, singleton


class Capabilities(dict):
    """A collection of feature flags. Corresponds to JSON properties in the DAP
    "initialize" request, other than those that identify the party.
    """

    PROPERTIES = {}
    """JSON property names and default values for the the capabilities represented
    by instances of this class. Keys are names, and values are either default values
    or validators.

    If the value is callable, it is a validator. The validator is invoked with the
    actual value of the JSON property passed to it as the sole argument; or if the
    property is missing in JSON, then () is passed. The validator must either raise
    ValueError describing why the property value is invalid, or return the value;
    in case where () was passed, it must return the default value replacing that.

    If the value is not callable, it is as if default(value) validator was used.
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
                validate = default(validate)

            try:
                value = validate(value)
            except Exception as exc:
                message.isnt_valid("{0!r} {1}", name, exc)

            assert value != (), fmt(
                "{0!r} must provide a default value for missing properties.", validate
            )
            self[name] = value

        log.info("{0}", self)

    def __repr__(self):
        return fmt("{0}: {1!j}", type(self).__name__, dict(self))


def default(default):
    """Returns a validator for a JSON property with a default value.

    The validator will only allow property values that have the same type as the
    specified default value.
    """

    def validate(value):
        if value == ():
            return default
        elif isinstance(value, type(default)):
            return value
        else:
            raise ValueError(fmt("must be a {0}", type(default).__name__))

    return validate


def enum(*values):
    """Returns a validator for a JSON enum.

    The validator will only allow property values that match one of those specified.
    If property is missing, the first value specified is used as the default.
    """

    def validate(value):
        if value == ():
            return values[0]
        elif value in values:
            return value
        else:
            raise ValueError(fmt("must be one of: {0!r}", list(values)))

    assert len(values)
    return validate


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
        "pathFormat": enum("path", "uri"),
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
