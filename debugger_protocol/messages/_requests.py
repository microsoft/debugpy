from debugger_protocol.arg import FieldsNamespace, Field, Enum
from .shared import Checksum, Source


class Message(FieldsNamespace):
    """A structured message object.

    Used to return errors from requests.
    """
    FIELDS = [
        Field('id', int),
        Field('format'),
        Field.START_OPTIONAL,
        Field('variables', {str: str}),
        Field('sendTelemetry', bool),
        Field('showUser', bool),
        Field('url'),
        Field('urlLabel'),
    ]


class ExceptionBreakpointsFilter(FieldsNamespace):
    """
    An ExceptionBreakpointsFilter is shown in the UI as an option for
    configuring how exceptions are dealt with.
    """

    FIELDS = [
        Field('filter'),
        Field('label'),
        Field.START_OPTIONAL,
        Field('default', bool),
    ]


class ColumnDescriptor(FieldsNamespace):
    """
    A ColumnDescriptor specifies what module attribute to show in a
    column of the ModulesView, how to format it, and what the column's
    label should be.  It is only used if the underlying UI actually
    supports this level of customization.
    """

    TYPES = {"string", "number", "boolean", "unixTimestampUTC"}
    FIELDS = [
        Field('attributeName'),
        Field('label'),
        Field.START_OPTIONAL,
        Field('format'),
        Field('type'),
        Field('width', int),
    ]


class Capabilities(FieldsNamespace):
    """Information about the capabilities of a debug adapter."""

    FIELDS = [
        Field.START_OPTIONAL,
        Field('supportsConfigurationDoneRequest', bool),
        Field('supportsFunctionBreakpoints', bool),
        Field('supportsConditionalBreakpoints', bool),
        Field('supportsHitConditionalBreakpoints', bool),
        Field('supportsEvaluateForHovers', bool),
        Field('exceptionBreakpointFilters', [ExceptionBreakpointsFilter]),
        Field('supportsStepBack', bool),
        Field('supportsSetVariable', bool),
        Field('supportsRestartFrame', bool),
        Field('supportsGotoTargetsRequest', bool),
        Field('supportsStepInTargetsRequest', bool),
        Field('supportsCompletionsRequest', bool),
        Field('supportsModulesRequest', bool),
        Field('additionalModuleColumns', [ColumnDescriptor]),
        Field('supportedChecksumAlgorithms', [Enum(str, Checksum.ALGORITHMS)]),
        Field('supportsRestartRequest', bool),
        Field('supportsExceptionOptions', bool),
        Field('supportsValueFormattingOptions', bool),
        Field('supportsExceptionInfoRequest', bool),
        Field('supportTerminateDebuggee', bool),
        Field('supportsDelayedStackTraceLoading', bool),
        Field('supportsLoadedSourcesRequest', bool),
        Field('supportsSetExpression', bool),
        Field('supportsModulesRequest', bool),
    ]


class ModulesViewDescriptor(FieldsNamespace):
    """
    The ModulesViewDescriptor is the container for all declarative
    configuration options of a ModuleView.  For now it only specifies
    the columns to be shown in the modules view.
    """

    FIELDS = [
        Field('columns', [ColumnDescriptor]),
    ]


class Thread(FieldsNamespace):
    """A thread."""

    FIELDS = [
        Field('id', int),
        Field('name'),
    ]


class StackFrame(FieldsNamespace):
    """A Stackframe contains the source location."""

    PRESENTATION_HINTS = {"normal", "label", "subtle"}
    FIELDS = [
        Field('id', int),
        Field('name'),
        Field('source', Source, optional=True),
        Field('line', int),
        Field('column', int),
        Field.START_OPTIONAL,
        Field('endLine', int),
        Field('endColumn', int),
        Field("moduleId", {int, str}),
        Field('presentationHint'),
    ]


class Scope(FieldsNamespace):
    """
    A Scope is a named container for variables.  Optionally a scope
    can map to a source or a range within a source.
    """

    FIELDS = [
        Field('name'),
        Field('variablesReference', int),
        Field('namedVariables', int, optional=True),
        Field('indexedVariables', int, optional=True),
        Field('expensive', bool),
        Field.START_OPTIONAL,
        Field('source', Source),
        Field('line', int),
        Field('column', int),
        Field('endLine', int),
        Field('endColumn', int),
    ]


class VariablePresentationHint(FieldsNamespace):
    """
    Optional properties of a variable that can be used to determine
    how to render the variable in the UI.
    """

    KINDS = {"property", "method", "class", "data", "event", "baseClass",
             "innerClass", "interface", "mostDerivedClass", "virtual"}
    ATTRIBUTES = {"static", "constant", "readOnly", "rawString",
                  "hasObjectId", "canHaveObjectId", "hasSideEffects"}
    VISIBILITIES = {"public", "private", "protected", "internal", "final"}
    FIELDS = [
        Field.START_OPTIONAL,
        Field('kind', enum=KINDS),
        Field('attributes', [Enum(str, ATTRIBUTES)]),
        Field('visibility', enum=VISIBILITIES),
    ]


class Variable(FieldsNamespace):
    """A Variable is a name/value pair.

    Optionally a variable can have a 'type' that is shown if space
    permits or when hovering over the variable's name.  An optional
    'kind' is used to render additional properties of the variable,
    e.g. different icons can be used to indicate that a variable is
    public or private.  If the value is structured (has children), a
    handle is provided to retrieve the children with the
    VariablesRequest.  If the number of named or indexed children is
    large, the numbers should be returned via the optional
    'namedVariables' and 'indexedVariables' attributes.  The client can
    use this optional information to present the children in a paged UI
    and fetch them in chunks.
    """

    FIELDS = [
        Field('name'),
        Field('value'),
        Field.START_OPTIONAL,
        Field('type'),
        Field('presentationHint', VariablePresentationHint),
        Field('evaluateName'),
        Field('variablesReference', int, optional=False),
        Field('namedVariables', int),
        Field('indexedVariables', int),
    ]


class SourceBreakpoint(FieldsNamespace):
    """Properties of a breakpoint passed to the setBreakpoints request."""

    FIELDS = [
        Field('line', int),
        Field.START_OPTIONAL,
        Field('column', int),
        Field('condition'),
        Field('hitCondition'),
    ]


class FunctionBreakpoint(FieldsNamespace):
    """
    Properties of a breakpoint passed to the setFunctionBreakpoints request.
    """

    FIELDS = [
        Field('name'),
        Field.START_OPTIONAL,
        Field('condition'),
        Field('hitCondition'),
    ]


class StepInTarget(FieldsNamespace):
    """
    A StepInTarget can be used in the 'stepIn' request and determines
    into which single target the stepIn request should step.
    """

    FIELDS = [
        Field('id', int),
        Field('label'),
    ]


class GotoTarget(FieldsNamespace):
    """
    A GotoTarget describes a code location that can be used as a target
    in the 'goto' request.  The possible goto targets can be determined
    via the 'gotoTargets' request.
    """

    FIELDS = [
        Field('id', int),
        Field('label'),
        Field('line', int),
        Field.START_OPTIONAL,
        Field('column', int),
        Field('endLine', int),
        Field('endColumn', int),
    ]


class CompletionItem(FieldsNamespace):
    """
    CompletionItems are the suggestions returned from the CompletionsRequest.
    """

    TYPES = {"method", "function", "constructor", "field", "variable",
             "class", "interface", "module", "property", "unit", "value",
             "enum", "keyword", "snippet", "text", "color", "file",
             "reference", "customcolor"}
    FIELDS = [
        Field('label'),
        Field.START_OPTIONAL,
        Field('text'),
        Field('type'),
        Field('start', int),
        Field('length', int),
    ]


class ValueFormat(FieldsNamespace):
    """Provides formatting information for a value."""

    FIELDS = [
        Field.START_OPTIONAL,
        Field('hex', bool),
    ]


class StackFrameFormat(ValueFormat):
    """Provides formatting information for a stack frame."""

    FIELDS = ValueFormat.FIELDS + [
        Field('parameters', bool),
        Field('parameterTypes', bool),
        Field('parameterNames', bool),
        Field('parameterValues', bool),
        Field('line', bool),
        Field('module', bool),
        Field('includeAll', bool),
    ]


class ExceptionPathSegment(FieldsNamespace):
    """
    An ExceptionPathSegment represents a segment in a path that is used
    to match leafs or nodes in a tree of exceptions. If a segment
    consists of more than one name, it matches the names provided if
    'negate' is false or missing or it matches anything except the names
    provided if 'negate' is true.
    """

    FIELDS = [
        Field('negate', bool, optional=True),
        Field('names', [str]),
    ]


ExceptionBreakMode = Enum(str,
                          {"never", "always", "unhandled", "userUnhandled"})


class ExceptionOptions(FieldsNamespace):
    """
    An ExceptionOptions assigns configuration options to a set of exceptions.
    """

    FIELDS = [
        Field('path', [ExceptionPathSegment], optional=True),
        Field('breakMode', ExceptionBreakMode),
    ]


class ExceptionDetails(FieldsNamespace):
    """Detailed information about an exception that has occurred."""

    FIELDS = [
        Field.START_OPTIONAL,
        Field('message'),
        Field('typeName'),
        Field('fullTypeName'),
        Field('evaluateName'),
        Field('stackTrace'),
        Field('innerException', ['<ref>']),
    ]
