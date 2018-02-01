from debugger_protocol.arg import ANY, FieldsNamespace, Field


FIELDS_BASIC = [
    Field('name'),
    Field.START_OPTIONAL,
    Field('value'),
]

BASIC_FULL = {
    'name': 'spam',
    'value': 'eggs',
}

BASIC_MIN = {
    'name': 'spam',
}


class Basic(FieldsNamespace):
    FIELDS = FIELDS_BASIC


FIELDS_EXTENDED = [
    Field('name', datatype=str, optional=False),
    Field('valid', datatype=bool, optional=True),
    Field('id', datatype=int, optional=False),
    Field('value', datatype=ANY, optional=True),
    Field('x', datatype=Basic, optional=True),
    Field('y', datatype={int, str}, optional=True),
    Field('z', datatype=[Basic], optional=True),
]

EXTENDED_FULL = {
    'name': 'spam',
    'valid': True,
    'id': 10,
    'value': None,
    'x': BASIC_FULL,
    'y': 11,
    'z': [
        BASIC_FULL,
        BASIC_MIN,
    ],
}

EXTENDED_MIN = {
    'name': 'spam',
    'id': 10,
}
