import unittest

from debugger_protocol.arg import NOT_SET, ANY
from debugger_protocol.arg._datatype import FieldsNamespace
from debugger_protocol.arg._decl import (
    REF, TYPE_REFERENCE, _normalize_datatype, _transform_datatype,
    Enum, Union, Array, Field, Fields)
from debugger_protocol.arg._param import Parameter, DatatypeHandler, Arg
from debugger_protocol.arg._params import (
    SimpleParameter, UnionParameter, ArrayParameter, ComplexParameter)


class ModuleTests(unittest.TestCase):

    def test_normalize_datatype(self):
        NOOP = object()
        tests = [
            # explicitly handled
            (REF, TYPE_REFERENCE),
            (TYPE_REFERENCE, NOOP),
            (ANY, NOOP),
            (None, NOOP),
            (int, NOOP),
            (str, NOOP),
            (bool, NOOP),
            (Enum(str, ('spam',)), NOOP),
            (Union(str, int), NOOP),
            ({str, int}, Union(str, int)),
            (frozenset([str, int]), Union(str, int)),
            (Array(str), NOOP),
            ([str], Array(str)),
            ((str,), Array(str)),
            # others
            (Field('spam'), NOOP),
            (Fields(Field('spam')), NOOP),
            (Parameter(object()), NOOP),
            (ParameterImplBase(str), NOOP),
            (Arg(object(), object()), NOOP),
            (SimpleParameter(str), NOOP),
            (UnionParameter(Union(str)), NOOP),
            (ArrayParameter(Array(str)), NOOP),
            (ComplexParameter(Fields()), NOOP),
            (NOT_SET, NOOP),
            (object(), NOOP),
            (object, NOOP),
            (type, NOOP),
        ]
        for datatype, expected in tests:
            if expected is NOOP:
                expected = datatype
            with self.subTest(datatype):
                datatype = _normalize_datatype(datatype)

                self.assertEqual(datatype, expected)

        with self.assertRaises(NotImplementedError):
            _normalize_datatype({1: 2})

    def test_transform_datatype_simple(self):
        datatypes = [
            REF,
            TYPE_REFERENCE,
            ANY,
            None,
            int,
            str,
            bool,
            {str, int},
            frozenset([str, int]),
            [str],
            (str,),
            Parameter(object()),
            ParameterImplBase(str),
            Arg(object(), object()),
            SimpleParameter(str),
            UnionParameter(Union(str, int)),
            ArrayParameter(Array(str)),
            ComplexParameter(Fields()),
            NOT_SET,
            object(),
            object,
            type,
        ]
        for expected in datatypes:
            transformed = []
            op = (lambda dt: transformed.append(dt) or dt)
            with self.subTest(expected):
                datatype = _transform_datatype(expected, op)

                self.assertIs(datatype, expected)
                self.assertEqual(transformed, [expected])

    def test_transform_datatype_container(self):
        class Spam(FieldsNamespace):
            FIELDS = [
                Field('a'),
            ]

        Spam.normalize()

        fields = Fields(Field('...'))
        field_spam = Field('spam', ANY)
        field_ham = Field('ham', Union(
            Array(Spam),
        ))
        field_eggs = Field('eggs', Array(TYPE_REFERENCE))
        nested = Fields(
            Field('???', fields),
            field_spam,
            field_ham,
            field_eggs,
        )
        tests = {
            Array(str): [
                str,
                Array(str),
            ],
            Field('...'): [
                str,
                Field('...'),
            ],
            fields: [
                str,
                Field('...'),
                fields,
            ],
            nested: [
                str,
                Field('...'),
                fields,
                Field('???', fields),
                # ...
                ANY,
                Field('spam', ANY),
                # ...
                str,
                Field('a'),
                Fields(Field('a')),
                Spam,
                Array(Spam),
                Union(Array(Spam)),
                field_ham,
                # ...
                TYPE_REFERENCE,
                Array(TYPE_REFERENCE),
                field_eggs,
                # ...
                nested,
            ],
        }
        for datatype, expected in tests.items():
            calls = []
            op = (lambda dt: calls.append(dt) or dt)
            with self.subTest(datatype):
                transformed = _transform_datatype(datatype, op)

                self.assertIs(transformed, datatype)
                self.assertEqual(calls, expected)

        # Check Union separately due to set iteration order.
        calls = []
        op = (lambda dt: calls.append(dt) or dt)
        datatype = Union(str, int)
        transformed = _transform_datatype(datatype, op)

        self.assertIs(transformed, datatype)
        self.assertEqual(set(calls[:2]), {str, int})
        self.assertEqual(calls[2:], [
            Union(str, int),
        ])


class EnumTests(unittest.TestCase):

    def test_attrs(self):
        enum = Enum(str, ('spam', 'eggs'))
        datatype, choices = enum

        self.assertIs(datatype, str)
        self.assertEqual(choices, frozenset(['spam', 'eggs']))

    def test_bad_datatype(self):
        with self.assertRaises(ValueError):
            Enum('spam', ('spam', 'eggs'))
        with self.assertRaises(ValueError):
            Enum(dict, ('spam', 'eggs'))

    def test_bad_choices(self):
        class String(str):
            pass

        with self.assertRaises(ValueError):
            Enum(str, 'spam')
        with self.assertRaises(TypeError):
            Enum(str, ())
        with self.assertRaises(ValueError):
            Enum(str, ('spam', 10))
        with self.assertRaises(ValueError):
            Enum(str, ('spam', String))


class UnionTests(unittest.TestCase):

    def test_normalized(self):
        tests = [
            (REF, TYPE_REFERENCE),
            ({str, int}, Union(*{str, int})),
            (frozenset([str, int]), Union(*frozenset([str, int]))),
            ([str], Array(str)),
            ((str,), Array(str)),
            (None, None),
        ]
        for datatype, expected in tests:
            with self.subTest(datatype):
                union = Union(int, datatype, str)

                self.assertEqual(union, Union(int, expected, str))

        with self.assertRaises(NotImplementedError):
            Union({1: 2})

    def test_traverse_noop(self):
        calls = []
        op = (lambda dt: calls.append(dt) or dt)
        union = Union(str, Array(int), int)
        transformed = union.traverse(op)

        self.assertIs(transformed, union)
        self.assertCountEqual(calls, [
            str,
            # Note that it did not recurse into Array(int).
            Array(int),
            int,
        ])

    def test_traverse_changed(self):
        calls = []
        op = (lambda dt: calls.append(dt) or str)
        union = Union(ANY)
        transformed = union.traverse(op)

        self.assertIsNot(transformed, union)
        self.assertEqual(transformed, Union(str))
        self.assertEqual(calls, [
            ANY,
        ])


class ArrayTests(unittest.TestCase):

    def test_normalized(self):
        tests = [
            (REF, TYPE_REFERENCE),
            ({str, int}, Union(str, int)),
            (frozenset([str, int]), Union(str, int)),
            ([str], Array(str)),
            ((str,), Array(str)),
            (None, None),
        ]
        for datatype, expected in tests:
            with self.subTest(datatype):
                array = Array(datatype)

                self.assertEqual(array, Array(expected))

        with self.assertRaises(NotImplementedError):
            Array({1: 2})

    def test_traverse_noop(self):
        calls = []
        op = (lambda dt: calls.append(dt) or dt)
        array = Array(Union(str, int))
        transformed = array.traverse(op)

        self.assertIs(transformed, array)
        self.assertCountEqual(calls, [
            # Note that it did not recurse into Union(str, int).
            Union(str, int),
        ])

    def test_traverse_changed(self):
        calls = []
        op = (lambda dt: calls.append(dt) or str)
        array = Array(ANY)
        transformed = array.traverse(op)

        self.assertIsNot(transformed, array)
        self.assertEqual(transformed, Array(str))
        self.assertEqual(calls, [
            ANY,
        ])


class FieldTests(unittest.TestCase):

    def test_defaults(self):
        field = Field('spam')

        self.assertEqual(field.name, 'spam')
        self.assertIs(field.datatype, str)
        self.assertIs(field.default, NOT_SET)
        self.assertFalse(field.optional)

    def test_enum(self):
        field = Field('spam', str, enum=('a', 'b', 'c'))

        self.assertEqual(field.datatype, Enum(str, ('a', 'b', 'c')))

    def test_normalized(self):
        tests = [
            (REF, TYPE_REFERENCE),
            ({str, int}, Union(str, int)),
            (frozenset([str, int]), Union(str, int)),
            ([str], Array(str)),
            ((str,), Array(str)),
            (None, None),
        ]
        for datatype, expected in tests:
            with self.subTest(datatype):
                field = Field('spam', datatype)

                self.assertEqual(field, Field('spam', expected))

        with self.assertRaises(NotImplementedError):
            Field('spam', {1: 2})

    def test_traverse_noop(self):
        calls = []
        op = (lambda dt: calls.append(dt) or dt)
        field = Field('spam', Union(str, int))
        transformed = field.traverse(op)

        self.assertIs(transformed, field)
        self.assertCountEqual(calls, [
            # Note that it did not recurse into Union(str, int).
            Union(str, int),
        ])

    def test_traverse_changed(self):
        calls = []
        op = (lambda dt: calls.append(dt) or str)
        field = Field('spam', ANY)
        transformed = field.traverse(op)

        self.assertIsNot(transformed, field)
        self.assertEqual(transformed, Field('spam', str))
        self.assertEqual(calls, [
            ANY,
        ])


class FieldsTests(unittest.TestCase):

    def test_single(self):
        fields = Fields(
            Field('spam'),
        )

        self.assertEqual(fields, [
            Field('spam'),
        ])

    def test_multiple(self):
        fields = Fields(
            Field('spam'),
            Field('ham'),
            Field('eggs'),
        )

        self.assertEqual(fields, [
            Field('spam'),
            Field('ham'),
            Field('eggs'),
        ])

    def test_empty(self):
        fields = Fields()

        self.assertCountEqual(fields, [])

    def test_normalized(self):
        tests = [
            (REF, TYPE_REFERENCE),
            ({str, int}, Union(str, int)),
            (frozenset([str, int]), Union(str, int)),
            ([str], Array(str)),
            ((str,), Array(str)),
            (None, None),
        ]
        for datatype, expected in tests:
            with self.subTest(datatype):
                fields = Fields(
                    Field('spam', datatype),
                )

                self.assertEqual(fields, [
                    Field('spam', expected),
                ])

        with self.assertRaises(NotImplementedError):
            Fields(
                Field('spam', {1: 2}),
            )

    def test_with_START_OPTIONAL(self):
        fields = Fields(
            Field('spam'),
            Field('ham', optional=True),
            Field('eggs'),
            Field.START_OPTIONAL,
            Field('a'),
            Field('b', optional=False),
        )

        self.assertEqual(fields, [
            Field('spam'),
            Field('ham', optional=True),
            Field('eggs'),
            Field('a', optional=True),
            Field('b', optional=True),
        ])

    def test_non_field(self):
        with self.assertRaises(TypeError):
            Fields(str)

    def test_as_dict(self):
        fields = Fields(
            Field('spam', int),
            Field('ham'),
            Field('eggs', Array(str)),
        )
        result = fields.as_dict

        self.assertEqual(result, {
            'spam': fields[0],
            'ham': fields[1],
            'eggs': fields[2],
            })

    def test_traverse_noop(self):
        calls = []
        op = (lambda dt: calls.append(dt) or dt)
        fields = Fields(
            Field('spam'),
            Field('ham'),
            Field('eggs'),
        )
        transformed = fields.traverse(op)

        self.assertIs(transformed, fields)
        self.assertCountEqual(calls, [
            # Note that it did not recurse into the fields.
            Field('spam'),
            Field('ham'),
            Field('eggs'),
        ])

    def test_traverse_changed(self):
        calls = []
        op = (lambda dt: calls.append(dt) or Field(dt.name, str))
        fields = Fields(
            Field('spam', ANY),
            Field('eggs', None),
        )
        transformed = fields.traverse(op)

        self.assertIsNot(transformed, fields)
        self.assertEqual(transformed, Fields(
            Field('spam', str),
            Field('eggs', str),
        ))
        self.assertEqual(calls, [
            Field('spam', ANY),
            Field('eggs', None),
        ])
