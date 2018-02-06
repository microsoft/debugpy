from debugger_protocol.arg import ANY, FieldsNamespace, Field
from . import register
from .shared import Breakpoint, Module, Source
from .message import Event


@register
class InitializedEvent(Event):
    """"Event message for 'initialized' event type.

    This event indicates that the debug adapter is ready to accept
    configuration requests (e.g. SetBreakpointsRequest,
    SetExceptionBreakpointsRequest).  A debug adapter is expected to
    send this event when it is ready to accept configuration requests
    (but not before the InitializeRequest has finished).

    The sequence of events/requests is as follows:
    - adapters sends InitializedEvent (after the InitializeRequest
      has returned)
    - frontend sends zero or more SetBreakpointsRequest
    - frontend sends one SetFunctionBreakpointsRequest
    - frontend sends a SetExceptionBreakpointsRequest if one or more
      exceptionBreakpointFilters have been defined (or if
      supportsConfigurationDoneRequest is not defined or false)
    - frontend sends other future configuration requests
    - frontend sends one ConfigurationDoneRequest to indicate the end
      of the configuration
    """

    EVENT = 'initialized'


@register
class StoppedEvent(Event):
    """Event message for 'stopped' event type.

    The event indicates that the execution of the debuggee has stopped
    due to some condition.  This can be caused by a break point
    previously set, a stepping action has completed, by executing a
    debugger statement etc.
    """

    EVENT = 'stopped'

    class BODY(FieldsNamespace):
        REASONS = {'step', 'breakpoint', 'exception', 'pause', 'entry'}
        FIELDS = [
            Field('reason', enum=REASONS),
            Field.START_OPTIONAL,
            Field('description'),
            Field('threadId', int),
            Field('text'),
            Field('allThreadsStopped', bool),
        ]


@register
class ContinuedEvent(Event):
    """Event message for 'continued' event type.

    The event indicates that the execution of the debuggee has
    continued.

    Please note: a debug adapter is not expected to send this event
    in response to a request that implies that execution continues,
    e.g. 'launch' or 'continue'.  It is only necessary to send a
    ContinuedEvent if there was no previous request that implied this.
    """

    EVENT = 'continued'

    class BODY(FieldsNamespace):
        FIELDS = [
            Field('threadId', int),
            Field.START_OPTIONAL,
            Field('allThreadsContinued', bool),
        ]


@register
class ExitedEvent(Event):
    """Event message for 'exited' event type.

    The event indicates that the debuggee has exited.
    """

    EVENT = 'exited'

    class BODY(FieldsNamespace):
        FIELDS = [
            Field('exitCode', int),
        ]


@register
class TerminatedEvent(Event):
    """Event message for 'terminated' event types.

    The event indicates that debugging of the debuggee has terminated.
    """

    EVENT = 'terminated'

    class BODY(FieldsNamespace):
        FIELDS = [
            Field.START_OPTIONAL,
            Field('restart', ANY),
        ]


@register
class ThreadEvent(Event):
    """Event message for 'thread' event type.

    The event indicates that a thread has started or exited.
    """

    EVENT = 'thread'

    class BODY(FieldsNamespace):
        REASONS = {'started', 'exited'}
        FIELDS = [
            Field('threadId', int),
            Field('reason', enum=REASONS),
        ]


@register
class OutputEvent(Event):
    """Event message for 'output' event type.

    The event indicates that the target has produced some output.
    """

    EVENT = 'output'

    class BODY(FieldsNamespace):
        CATEGORIES = {'console', 'stdout', 'stderr', 'telemetry'}
        FIELDS = [
            Field('output'),
            Field.START_OPTIONAL,
            Field('category', enum=CATEGORIES),
            Field('variablesReference', int),  # "number"
            Field('source'),
            Field('line', int),
            Field('column', int),
            Field('data', ANY),
        ]


@register
class BreakpointEvent(Event):
    """Event message for 'breakpoint' event type.

    The event indicates that some information about a breakpoint
    has changed.
    """

    EVENT = 'breakpoint'

    class BODY(FieldsNamespace):
        REASONS = {'changed', 'new', 'removed'}
        FIELDS = [
            Field('breakpoint', Breakpoint),
            Field('reason', enum=REASONS),
        ]


@register
class ModuleEvent(Event):
    """Event message for 'module' event type.

    The event indicates that some information about a module
    has changed.
    """

    EVENT = 'module'

    class BODY(FieldsNamespace):
        REASONS = {'new', 'changed', 'removed'}
        FIELDS = [
            Field('module', Module),
            Field('reason', enum=REASONS),
        ]


@register
class LoadedSourceEvent(Event):
    """Event message for 'loadedSource' event type.

    The event indicates that some source has been added, changed, or
    removed from the set of all loaded sources.
    """

    EVENT = 'loadedSource'

    class BODY(FieldsNamespace):
        REASONS = {'new', 'changed', 'removed'}
        FIELDS = [
            Field('source', Source),
            Field('reason', enum=REASONS),
        ]


@register
class ProcessEvent(Event):
    """Event message for 'process' event type.

    The event indicates that the debugger has begun debugging a new
    process. Either one that it has launched, or one that it has
    attached to.
    """

    EVENT = 'process'

    class BODY(FieldsNamespace):
        START_METHODS = {'launch', 'attach', 'attachForSuspendedLaunch'}
        FIELDS = [
            Field('name'),
            Field.START_OPTIONAL,
            Field('systemProcessId', int),
            Field('isLocalProcess', bool),
            Field('startMethod', enum=START_METHODS),
        ]


# Clean up the implicit __all__.
del register
del Event
del FieldsNamespace
del Field
del ANY
del Breakpoint
del Module
del Source
