# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import annotations
import typing

if typing.TYPE_CHECKING:
    __all__: list[str]

__all__ = ["CAPABILITIES", "access_token"]

EXCEPTION_FILTERS = [
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

CAPABILITIES_V1 = {
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
    "exceptionBreakpointFilters": EXCEPTION_FILTERS,
    "supportsStepInTargetsRequest": True,
}

CAPABILITIES_V2 = {
    "supportsConfigurationDoneRequest": True,
    "supportsConditionalBreakpoints": True,
    "supportsHitConditionalBreakpoints": True,
    "supportsEvaluateForHovers": True,
    "exceptionBreakpointFilters": EXCEPTION_FILTERS,
    "supportsSetVariable": True,
    "supportsExceptionInfoRequest": True,
    "supportsDelayedStackTraceLoading": True,
    "supportsLogPoints": True,
    "supportsSetExpression": True,
    "supportsTerminateRequest": True,
    "supportsClipboardContext": True,
    "supportsGotoTargetsRequest": True,
}

access_token = None
"""Access token used to authenticate with this adapter."""
