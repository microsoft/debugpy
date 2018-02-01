from debugger_protocol.arg import FieldsNamespace, Field
from . import register
from . import _requests as datatypes
from . import shared
from .message import Request, Response


@register
class ErrorResponse(Response):
    """An error response (for any unsuccessful request).

    On error (whenever 'success' is false) the body can provide more
    details.
    """

    COMMAND = 'error'

    class BODY(FieldsNamespace):
        FIELDS = [
            Field('error', datatypes.Message),
        ]


##################################

@register
class RunInTerminalRequest(Request):
    """runInTerminal request.

    With this request a debug adapter can run a command in a terminal.
    """

    COMMAND = 'runInTerminal'

    class ARGUMENTS(FieldsNamespace):
        KINDS = {'integrated', 'external'}
        FIELDS = [
            Field('kind', enum=KINDS, optional=True),
            Field('title', optional=True),
            Field('cwd'),
            Field('args', [str]),
            Field.START_OPTIONAL,
            Field('env', {str: {str, None}}),
        ]


@register
class RunInTerminalResponse(Response):
    COMMAND = 'runInTerminal'

    class BODY(FieldsNamespace):
        FIELDS = [
            Field('processId', int),  # number
        ]

    ERROR_BODY = ErrorResponse.BODY


##################################

@register
class InitializeRequest(Request):
    COMMAND = 'initialize'

    class ARGUMENTS(FieldsNamespace):
        PATH_FORMATS = {'path', 'uri'}
        FIELDS = [
            Field('clientID', optional=True),
            Field('adapterID'),
            Field.START_OPTIONAL,
            Field('locale'),
            Field('linesStartAt1', bool),
            Field('columnsStartAt1', bool),
            Field('pathFormat', enum=PATH_FORMATS),
            Field('supportsVariableType', bool),
            Field('supportsVariablePaging', bool),
            Field('supportsRunInTerminalRequest', bool),
        ]


@register
class InitializeResponse(Response):
    COMMAND = 'initialize'

    BODY = datatypes.Capabilities
    BODY_REQUIRED = False

    ERROR_BODY = ErrorResponse.BODY


##################################

@register
class ConfigurationDoneRequest(Request):
    """configurationDone request.

    The client of the debug protocol must send this request at the end
    of the sequence of configuration requests (which was started by
    the InitializedEvent).
    """

    COMMAND = 'configurationDone'

    ARGUMENTS_REQUIRED = False


@register
class ConfigurationDoneResponse(Response):
    COMMAND = 'configurationDone'

    # This is just an acknowledgement.
    BODY_REQUIRED = False

    ERROR_BODY = ErrorResponse.BODY


##################################

@register
class LaunchRequest(Request):
    COMMAND = 'launch'

    class ARGUMENTS(FieldsNamespace):
        FIELDS = [
            Field('noDebug', bool, optional=True, default=False),
        ]


@register
class LaunchResponse(Response):
    COMMAND = 'launch'

    # This is just an acknowledgement.
    BODY_REQUIRED = False

    ERROR_BODY = ErrorResponse.BODY


##################################

@register
class AttachRequest(Request):
    COMMAND = 'attach'

    ARGUMENTS_REQUIRED = False
    #class ARGUMENTS(FieldsNamespace):
    #    FIELDS = []


@register
class AttachResponse(Response):
    COMMAND = 'attach'

    # This is just an acknowledgement.
    BODY_REQUIRED = False

    ERROR_BODY = ErrorResponse.BODY


##################################

@register
class RestartRequest(Request):
    """restart request.

    Restarts a debug session. If the capability 'supportsRestartRequest'
    is missing or has the value false, the client will implement
    'restart' by terminating the debug adapter first and then launching
    it anew.  A debug adapter can override this default behaviour by
    implementing a restart request and setting the capability
    'supportsRestartRequest' to true.
    """

    COMMAND = 'restart'

    ARGUMENTS_REQUIRED = False


@register
class RestartResponse(Response):
    COMMAND = 'restart'

    # This is just an acknowledgement.
    BODY_REQUIRED = False

    ERROR_BODY = ErrorResponse.BODY


##################################

@register
class DisconnectRequest(Request):
    """disconnect request.

    terminateDebuggee: Indicates whether the debuggee should be
      terminated when the debugger is disconnected.  If unspecified,
      the debug adapter is free to do whatever it thinks is best.  A
      client can only rely on this attribute being properly honored if
      a debug adapter returns true for the 'supportTerminateDebuggee'
      capability.
    """

    COMMAND = 'disconnect'

    class ARGUMENTS(FieldsNamespace):
        FIELDS = [
            Field('terminateDebuggee', bool, optional=True),
        ]


@register
class DisconnectResponse(Response):
    COMMAND = 'disconnect'

    # This is just an acknowledgement.
    BODY_REQUIRED = False

    ERROR_BODY = ErrorResponse.BODY


##################################

@register
class SetBreakpointsRequest(Request):
    """setBreakpoints request.

    Sets multiple breakpoints for a single source and clears all
    previous breakpoints in that source.  To clear all breakpoint for
    a source, specify an empty array.  When a breakpoint is hit, a
    StoppedEvent (event type 'breakpoint') is generated.
    """

    COMMAND = 'setBreakpoints'

    class ARGUMENTS(FieldsNamespace):
        FIELDS = [
            Field('source', shared.Source),
            Field.START_OPTIONAL,
            Field('breakpoints', [datatypes.SourceBreakpoint]),
            Field('lines', [int]),
            Field('sourceModified', bool),
        ]


@register
class SetBreakpointsResponse(Response):
    COMMAND = 'setBreakpoints'

    class BODY(FieldsNamespace):
        FIELDS = [
            Field('breakpoints', [shared.Breakpoint]),
        ]

    ERROR_BODY = ErrorResponse.BODY


##################################

@register
class SetFunctionBreakpointsRequest(Request):
    """setFunctionBreakpoints request.

    Sets multiple function breakpoints and clears all previous function
    breakpoints.  To clear all function breakpoint, specify an empty
    array.  When a function breakpoint is hit, a StoppedEvent (event
    type 'function breakpoint') is generated.
    """

    COMMAND = 'setFunctionBreakpoints'

    class ARGUMENTS(FieldsNamespace):
        FIELDS = [
            Field('breakpoints', [datatypes.FunctionBreakpoint]),
        ]


@register
class SetFunctionBreakpointsResponse(Response):
    COMMAND = 'setFunctionBreakpoints'

    class BODY(FieldsNamespace):
        FIELDS = [
            Field('breakpoints', [shared.Breakpoint]),
        ]

    ERROR_BODY = ErrorResponse.BODY


##################################

@register
class SetExceptionBreakpointsRequest(Request):
    """setExceptionBreakpoints request.

    The request configures the debuggers response to thrown exceptions.
    If an exception is configured to break, a StoppedEvent is fired
    (event type 'exception').
    """

    COMMAND = 'setExceptionBreakpoints'

    class ARGUMENTS(FieldsNamespace):
        FIELDS = [
            Field('filters', [str]),
            Field.START_OPTIONAL,
            Field('exceptionOptions', [datatypes.ExceptionOptions]),
        ]


@register
class SetExceptionBreakpointsResponse(Response):
    COMMAND = 'setExceptionBreakpoints'

    # This is just an acknowledgement.
    BODY_REQUIRED = False

    ERROR_BODY = ErrorResponse.BODY


##################################

@register
class ContinueRequest(Request):
    """continue request.

    The request starts the debuggee to run again.

    threadId: Continue execution for the specified thread (if possible).
      If the backend cannot continue on a single thread but will
      continue on all threads, it should set the allThreadsContinued
      attribute in the response to true.
    """

    COMMAND = 'continue'

    class ARGUMENTS(FieldsNamespace):
        FIELDS = [
            Field('threadId', int),
        ]


@register
class ContinueResponse(Response):
    COMMAND = 'continue'

    class BODY(FieldsNamespace):
        FIELDS = [
            Field.START_OPTIONAL,
            Field('allThreadsContinued', bool),
        ]

    ERROR_BODY = ErrorResponse.BODY


##################################

@register
class NextRequest(Request):
    """next request.

    The request starts the debuggee to run again for one step.  The
    debug adapter first sends the NextResponse and then a StoppedEvent
    (event type 'step') after the step has completed.
    """

    COMMAND = 'next'

    class ARGUMENTS(FieldsNamespace):
        FIELDS = [
            Field('threadId', int),
        ]


@register
class NextResponse(Response):
    COMMAND = 'next'

    # This is just an acknowledgement.
    BODY_REQUIRED = False

    ERROR_BODY = ErrorResponse.BODY


##################################

@register
class StepInRequest(Request):
    """stepIn request.

    The request starts the debuggee to step into a function/method if
    possible.  If it cannot step into a target, 'stepIn' behaves like
    'next'.  The debug adapter first sends the StepInResponse and then
    a StoppedEvent (event type 'step') after the step has completed.
    If there are multiple function/method calls (or other targets) on
    the source line, the optional argument 'targetId' can be used to
    control into which target the 'stepIn' should occur.  The list of
    possible targets for a given source line can be retrieved via the
    'stepInTargets' request.
    """

    COMMAND = 'stepIn'

    class ARGUMENTS(FieldsNamespace):
        FIELDS = [
            Field('threadId', int),
            Field('targetId', int),
        ]


@register
class StepInResponse(Response):
    COMMAND = 'stepIn'

    # This is just an acknowledgement.
    BODY_REQUIRED = False

    ERROR_BODY = ErrorResponse.BODY


##################################

@register
class StepOutRequest(Request):
    """stepOut request.

    The request starts the debuggee to run again for one step.  The
    debug adapter first sends the StepOutResponse and then a
    StoppedEvent (event type 'step') after the step has completed.
    """

    COMMAND = 'stepOut'

    class ARGUMENTS(FieldsNamespace):
        FIELDS = [
            Field('threadId', int),
        ]


@register
class StepOutResponse(Response):
    COMMAND = 'stepOut'

    # This is just an acknowledgement.
    BODY_REQUIRED = False

    ERROR_BODY = ErrorResponse.BODY


##################################

@register
class StepBackRequest(Request):
    """stepBack request.

    The request starts the debuggee to run one step backwards.  The
    debug adapter first sends the StepBackResponse and then a
    StoppedEvent (event type 'step') after the step has completed.
    Clients should only call this request if the capability
    supportsStepBack is true.
    """

    COMMAND = 'stepBack'

    class ARGUMENTS(FieldsNamespace):
        FIELDS = [
            Field('threadId', int),
        ]


@register
class StepBackResponse(Response):
    COMMAND = 'stepBack'

    # This is just an acknowledgement.
    BODY_REQUIRED = False

    ERROR_BODY = ErrorResponse.BODY


##################################

@register
class ReverseContinueRequest(Request):
    """reverseContinue request.

    The request starts the debuggee to run backward.  Clients should
    only call this request if the capability supportsStepBack is true.
    """

    COMMAND = 'reverseContinue'

    class ARGUMENTS(FieldsNamespace):
        FIELDS = [
            Field('threadId', int),
        ]


@register
class ReverseContinueResponse(Response):
    COMMAND = 'reverseContinue'

    # This is just an acknowledgement.
    BODY_REQUIRED = False

    ERROR_BODY = ErrorResponse.BODY


##################################

@register
class RestartFrameRequest(Request):
    """restartFrame request.

    The request restarts execution of the specified stackframe.  The
    debug adapter first sends the RestartFrameResponse and then a
    StoppedEvent (event type 'restart') after the restart has
    completed.
    """

    COMMAND = 'restartFrame'

    class ARGUMENTS(FieldsNamespace):
        FIELDS = [
            Field('frameId', int),
        ]


@register
class RestartFrameResponse(Response):
    COMMAND = 'restartFrame'

    # This is just an acknowledgement.
    BODY_REQUIRED = False

    ERROR_BODY = ErrorResponse.BODY


##################################

@register
class GotoRequest(Request):
    """goto request.

    The request sets the location where the debuggee will continue to
    run.  This makes it possible to skip the execution of code or to
    executed code again.  The code between the current location and the
    goto target is not executed but skipped.  The debug adapter first
    sends the GotoResponse and then a StoppedEvent (event type 'goto').
    """

    COMMAND = 'goto'

    class ARGUMENTS(FieldsNamespace):
        FIELDS = [
            Field('threadId', int),
            Field('targetId', int),
        ]


@register
class GotoResponse(Response):
    COMMAND = 'goto'

    # This is just an acknowledgement.
    BODY_REQUIRED = False

    ERROR_BODY = ErrorResponse.BODY


##################################

@register
class PauseRequest(Request):
    """pause request.

    The request suspenses the debuggee.  The debug adapter first sends
    the PauseResponse and then a StoppedEvent (event type 'pause')
    after the thread has been paused successfully.
    """

    COMMAND = 'pause'

    class ARGUMENTS(FieldsNamespace):
        FIELDS = [
            Field('threadId', int),
        ]


@register
class PauseResponse(Response):
    COMMAND = 'pause'

    # This is just an acknowledgement.
    BODY_REQUIRED = False

    ERROR_BODY = ErrorResponse.BODY


##################################

@register
class StackTraceRequest(Request):
    """stackTrace request.

    The request returns a stacktrace from the current execution state.
    """

    COMMAND = 'stackTrace'

    class ARGUMENTS(FieldsNamespace):
        FIELDS = [
            Field('threadId', int),
            Field.START_OPTIONAL,
            Field('startFrame', int),
            Field('levels', int),
            Field('format', datatypes.StackFrameFormat),
        ]


@register
class StackTraceResponse(Response):
    COMMAND = 'stackTrace'

    class BODY(FieldsNamespace):
        FIELDS = [
            Field('stackFrames', [datatypes.StackFrame]),
            Field.START_OPTIONAL,
            Field('totalFrames', int),
        ]

    ERROR_BODY = ErrorResponse.BODY


##################################

@register
class ScopesRequest(Request):
    """scopes request.

    The request returns the variable scopes for a given stackframe ID.
    """

    COMMAND = 'scopes'

    class ARGUMENTS(FieldsNamespace):
        FIELDS = [
            Field('frameId', int),
        ]


@register
class ScopesResponse(Response):
    COMMAND = 'scopes'

    class BODY(FieldsNamespace):
        FIELDS = [
            Field('scopes', [datatypes.Scope]),
        ]

    ERROR_BODY = ErrorResponse.BODY


##################################

@register
class VariablesRequest(Request):
    """variables request.

    Retrieves all child variables for the given variable reference.  An
    optional filter can be used to limit the fetched children to either
    named or indexed children.
    """

    COMMAND = 'variables'

    class ARGUMENTS(FieldsNamespace):
        FILTERS = {'indexed', 'named'}
        FIELDS = [
            Field('variablesReference', int),
            Field.START_OPTIONAL,
            Field('filter', enum=FILTERS),
            Field('start', int),
            Field('count', int),
            Field('format', datatypes.ValueFormat),
        ]


@register
class VariablesResponse(Response):
    COMMAND = 'variables'

    class BODY(FieldsNamespace):
        FIELDS = [
            Field('variables', [datatypes.Variable]),
        ]

    ERROR_BODY = ErrorResponse.BODY


##################################

@register
class SetVariableRequest(Request):
    """setVariable request.

    Set the variable with the given name in the variable container
    to a new value.
    """

    COMMAND = 'setVariable'

    class ARGUMENTS(FieldsNamespace):
        FIELDS = [
            Field('variablesReference', int),
            Field('name'),
            Field('value'),
            Field.START_OPTIONAL,
            Field('format', datatypes.ValueFormat),
        ]


@register
class SetVariableResponse(Response):
    """
    """

    COMMAND = 'setVariable'

    class BODY(FieldsNamespace):
        FIELDS = [
            Field('value'),
            Field.START_OPTIONAL,
            Field('type'),
            Field('variablesReference', int),  # number
            Field('namedVariables', int),  # number
            Field('indexedVariables', int),  # number
        ]

    ERROR_BODY = ErrorResponse.BODY


##################################

@register
class SourceRequest(Request):
    """source request.

    The request retrieves the source code for a given source reference.
    """

    COMMAND = 'source'

    class ARGUMENTS(FieldsNamespace):
        FIELDS = [
            Field('source', shared.Source, optional=True),
            Field('sourceReference', int),
        ]


@register
class SourceResponse(Response):
    COMMAND = 'source'

    class BODY(FieldsNamespace):
        FIELDS = [
            Field('content'),
            Field.START_OPTIONAL,
            Field('mimeType'),
        ]

    ERROR_BODY = ErrorResponse.BODY


##################################

@register
class ThreadsRequest(Request):
    """threads request.

    The request retrieves a list of all threads.
    """

    COMMAND = 'threads'

    ARGUMENTS_REQUIRED = False


@register
class ThreadsResponse(Response):
    COMMAND = 'threads'

    class BODY(FieldsNamespace):
        FIELDS = [
            Field('threads', [datatypes.Thread]),
        ]

    ERROR_BODY = ErrorResponse.BODY


##################################

@register
class ModulesRequest(Request):
    """modules request.

    Modules can be retrieved from the debug adapter with the
    ModulesRequest which can either return all modules or a range of
    modules to support paging.
    """

    COMMAND = 'modules'

    class ARGUMENTS(FieldsNamespace):
        FIELDS = [
            Field.START_OPTIONAL,
            Field('startModule', int, default=0),
            Field('moduleCount', int),
        ]


@register
class ModulesResponse(Response):
    COMMAND = 'modules'

    class BODY(FieldsNamespace):
        FIELDS = [
            Field('modules', [shared.Module]),
            Field.START_OPTIONAL,
            Field('totalModules', int),
        ]

    ERROR_BODY = ErrorResponse.BODY


##################################

@register
class LoadedSourcesRequest(Request):
    """loadedSources request.

    Retrieves the set of all sources currently loaded by the debugged
    process.
    """

    COMMAND = 'loadedSources'

    ARGUMENTS_REQUIRED = False
    #class ARGUMENTS(FieldsNamespace):
    #    FIELDS = []


@register
class LoadedSourcesResponse(Response):
    COMMAND = 'loadedSources'

    class BODY(FieldsNamespace):
        FIELDS = [
            Field('sources', [shared.Source]),
        ]

    ERROR_BODY = ErrorResponse.BODY


##################################

@register
class EvaluateRequest(Request):
    """evaluate request.

    Evaluates the given expression in the context of the top most stack
    frame.  The expression has access to any variables and arguments
    that are in scope.
    """

    COMMAND = 'evaluate'

    class ARGUMENTS(FieldsNamespace):
        CONTEXTS = {'watch', 'repl', 'hover'}
        FIELDS = [
            Field('expression'),
            Field.START_OPTIONAL,
            Field('frameId', int),
            Field('context', enum=CONTEXTS),
            Field('format', datatypes.ValueFormat),
        ]


@register
class EvaluateResponse(Response):
    COMMAND = 'evaluate'

    class BODY(FieldsNamespace):
        FIELDS = [
            Field('result'),
            Field.START_OPTIONAL,
            Field('type'),
            Field('presentationHint', datatypes.VariablePresentationHint),
            Field('variablesReference', int, optional=False),  # number
            Field('namedVariables', int),  # number
            Field('indexedVariables', int),  # number
        ]

    ERROR_BODY = ErrorResponse.BODY


##################################

@register
class StepInTargetsRequest(Request):
    """stepInTargets request.

    This request retrieves the possible stepIn targets for the specified
    stack frame.  These targets can be used in the 'stepIn' request.
    The StepInTargets may only be called if the
    'supportsStepInTargetsRequest' capability exists and is true.
    """

    COMMAND = 'stepInTargets'

    class ARGUMENTS(FieldsNamespace):
        FIELDS = [
            Field('frameId', int),
        ]


@register
class StepInTargetsResponse(Response):
    COMMAND = 'stepInTargets'

    class BODY(FieldsNamespace):
        FIELDS = [
            Field('targets', [datatypes.StepInTarget]),
        ]

    ERROR_BODY = ErrorResponse.BODY


##################################

@register
class GotoTargetsRequest(Request):
    """gotoTargets request.

    This request retrieves the possible goto targets for the specified
    source location.  These targets can be used in the 'goto' request.
    The GotoTargets request may only be called if the
    'supportsGotoTargetsRequest' capability exists and is true.
    """

    COMMAND = 'gotoTargets'

    class ARGUMENTS(FieldsNamespace):
        FIELDS = [
            Field('source', shared.Source),
            Field('line', int),
            Field.START_OPTIONAL,
            Field('column', int),
        ]


@register
class GotoTargetsResponse(Response):
    COMMAND = 'gotoTargets'

    class BODY(FieldsNamespace):
        FIELDS = [
            Field('targets', [datatypes.GotoTarget]),
        ]

    ERROR_BODY = ErrorResponse.BODY


##################################

@register
class CompletionsRequest(Request):
    """completions request.

    Returns a list of possible completions for a given caret position
    and text.  The CompletionsRequest may only be called if the
    'supportsCompletionsRequest' capability exists and is true.
    """

    COMMAND = 'completions'

    class ARGUMENTS(FieldsNamespace):
        FIELDS = [
            Field('frameId', int, optional=True),
            Field('text'),
            Field('column', int),
            Field.START_OPTIONAL,
            Field('line', int),
        ]


@register
class CompletionsResponse(Response):
    COMMAND = 'completions'

    class BODY(FieldsNamespace):
        FIELDS = [
            Field('targets', [datatypes.CompletionItem]),
        ]

    ERROR_BODY = ErrorResponse.BODY


##################################

@register
class ExceptionInfoRequest(Request):
    """exceptionInfo request.

    Retrieves the details of the exception that caused the StoppedEvent
    to be raised.
    """

    COMMAND = 'exceptionInfo'

    class ARGUMENTS(FieldsNamespace):
        FIELDS = [
            Field('threadId', int),
        ]


@register
class ExceptionInfoResponse(Response):
    COMMAND = 'exceptionInfo'

    class BODY(FieldsNamespace):
        FIELDS = [
            Field('exceptionId'),
            Field('description', optional=True),
            Field('breakMode', datatypes.ExceptionBreakMode),
            Field.START_OPTIONAL,
            Field('details', datatypes.ExceptionDetails),
        ]

    ERROR_BODY = ErrorResponse.BODY


# Clean up the implicit __all__.
del register
del Request
del Response
del FieldsNamespace
del Field
del datatypes
del shared
