from debugger_protocol.arg import ANY, FieldsNamespace, Field


class Checksum(FieldsNamespace):
    """The checksum of an item calculated by the specified algorithm."""

    ALGORITHMS = {'MD5', 'SHA1', 'SHA256', 'timestamp'}

    FIELDS = [
        Field('algorithm', enum=ALGORITHMS),
        Field('checksum'),
    ]


class Source(FieldsNamespace):
    """A Source is a descriptor for source code.

    It is returned from the debug adapter as part of a StackFrame
    and it is used by clients when specifying breakpoints.
    """

    HINTS = {'normal', 'emphasize', 'deemphasize'}

    FIELDS = [
        Field.START_OPTIONAL,
        Field('name'),
        Field('path'),
        Field('sourceReference', int),  # number
        Field('presentationHint', enum=HINTS),
        Field('origin'),
        Field('sources', ['<ref>']),
        Field('adapterData', ANY),
        Field('checksums', [Checksum]),
    ]


class Breakpoint(FieldsNamespace):
    """Information about a Breakpoint.

    The breakpoint comes from setBreakpoints or setFunctionBreakpoints.
    """

    FIELDS = [
        Field('id', int, optional=True),
        Field('verified', bool),
        Field.START_OPTIONAL,
        Field('message'),
        Field('source', Source),
        Field('line', int),
        Field('column', int),
        Field('endLine', int),
        Field('endColumn', int),
    ]


class Module(FieldsNamespace):
    """A Module object represents a row in the modules view.

    Two attributes are mandatory: an id identifies a module in the
    modules view and is used in a ModuleEvent for identifying a module
    for adding, updating or deleting.  The name is used to minimally
    render the module in the UI.

    Additional attributes can be added to the module. They will show up
    in the module View if they have a corresponding ColumnDescriptor.

    To avoid an unnecessary proliferation of additional attributes with
    similar semantics but different names we recommend to re-use
    attributes from the 'recommended' list below first, and only
    introduce new attributes if nothing appropriate could be found.
    """

    FIELDS = [
        Field('id', {int, str}),
        Field('name'),
        Field.START_OPTIONAL,
        Field('path'),
        Field('isOptimized', bool),
        Field('isUserCode', bool),
        Field('version'),
        Field('symbolStatus'),
        Field('symbolFilePath'),
        Field('dateTimeStamp'),
        Field('addressRange'),
    ]
