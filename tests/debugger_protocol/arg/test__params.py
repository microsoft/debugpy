import unittest

from debugger_protocol.arg._common import NOT_SET, ANY
from debugger_protocol.arg._decl import Enum, Union, Array, Field, Fields
from debugger_protocol.arg._param import Parameter, DatatypeHandler
from debugger_protocol.arg._params import (
    param_from_datatype,
    NoopParameter, SingletonParameter,
    SimpleParameter, EnumParameter,
    UnionParameter, ArrayParameter, ComplexParameter)

from ._common import FIELDS_BASIC, BASIC_FULL, Basic


class String(str):
    pass


class Integer(int):
    pass


class ParamFromDatatypeTest(unittest.TestCase):

    def test_supported(self):
        handler = DatatypeHandler(str)
        tests = [
            (Parameter(str), Parameter(str)),
            (handler, Parameter(str, handler)),
            (Fields(Field('spam')), ComplexParameter(Fields(Field('spam')))),
            (Field('spam'), SimpleParameter(str)),
            (Field('spam', str, enum={'a'}), EnumParameter(str, {'a'})),
            (ANY, NoopParameter()),
            (None, SingletonParameter(None)),
            (str, SimpleParameter(str)),
            (int, SimpleParameter(int)),
            (bool, SimpleParameter(bool)),
            (Enum(str, {'a'}), EnumParameter(str, {'a'})),
            (Union(str, int), UnionParameter(Union(str, int))),
            ({str, int}, UnionParameter(Union(str, int))),
            (frozenset([str, int]), UnionParameter(Union(str, int))),
            (Array(str), ArrayParameter(Array(str))),
            ([str], ArrayParameter(Array(str))),
            ((str,), ArrayParameter(Array(str))),
            (Basic, ComplexParameter(Basic)),
        ]
        for datatype, expected in tests:
            with self.subTest(datatype):
                param = param_from_datatype(datatype)

                self.assertEqual(param, expected)

    def test_not_supported(self):
        datatypes = [
            String('spam'),
            ...,
        ]
        for datatype in datatypes:
            with self.subTest(datatype):
                with self.assertRaises(NotImplementedError):
                    param_from_datatype(datatype)


class NoopParameterTests(unittest.TestCase):

    VALUES = [
        object(),
        'spam',
        10,
        ['spam'],
        {'spam': 42},
        True,
        None,
        NOT_SET,
    ]

    def test_match_type(self):
        values = [
            object(),
            '',
            'spam',
            b'spam',
            0,
            10,
            10.0,
            10+0j,
            ('spam',),
            (),
            ['spam'],
            [],
            {'spam': 42},
            {},
            {'spam'},
            set(),
            object,
            type,
            NoopParameterTests,
            True,
            None,
            ...,
            NotImplemented,
            NOT_SET,
            ANY,
            Union(str, int),
            Union(),
            Array(str),
            Field('spam'),
            Fields(Field('spam')),
            Fields(),
            Basic,
        ]
        for value in values:
            with self.subTest(value):
                param = NoopParameter()
                handler = param.match_type(value)

                self.assertIs(type(handler), DatatypeHandler)
                self.assertIs(handler.datatype, ANY)

    def test_coerce(self):
        for value in self.VALUES:
            with self.subTest(value):
                param = NoopParameter()
                handler = param.match_type(value)
                coerced = handler.coerce(value)

                self.assertIs(coerced, value)

    def test_validate(self):
        for value in self.VALUES:
            with self.subTest(value):
                param = NoopParameter()
                handler = param.match_type(value)
                handler.validate(value)

    def test_as_data(self):
        for value in self.VALUES:
            with self.subTest(value):
                param = NoopParameter()
                handler = param.match_type(value)
                data = handler.as_data(value)

                self.assertIs(data, value)


class SingletonParameterTests(unittest.TestCase):

    def test_match_type_matched(self):
        param = SingletonParameter(None)
        handler = param.match_type(None)

        self.assertIs(handler.datatype, None)

    def test_match_type_no_match(self):
        tests = [
            # same type, different value
            ('spam', 'eggs'),
            (10, 11),
            (True, False),
            # different type but equivalent
            ('spam', b'spam'),
            (10, 10.0),
            (10, 10+0j),
            (10, '10'),
            (10, b'\10'),
        ]
        for singleton, value in tests:
            with self.subTest((singleton, value)):
                param = SingletonParameter(singleton)
                handler = param.match_type(value)

                self.assertIs(handler, None)

    def test_coerce(self):
        param = SingletonParameter(None)
        handler = param.match_type(None)
        value = handler.coerce(None)

        self.assertIs(value, None)

    def test_validate_valid(self):
        param = SingletonParameter(None)
        handler = param.match_type(None)
        handler.validate(None)

    def test_validate_wrong_type(self):
        tests = [
            (None, True),
            (True, None),
            ('spam', 10),
            (10, 'spam'),
        ]
        for singleton, value in tests:
            with self.subTest(singleton):
                param = SingletonParameter(singleton)
                handler = param.match_type(singleton)

                with self.assertRaises(ValueError):
                    handler.validate(value)

    def test_validate_same_type_wrong_value(self):
        tests = [
            ('spam', 'eggs'),
            (True, False),
            (10, 11),
        ]
        for singleton, value in tests:
            with self.subTest(singleton):
                param = SingletonParameter(singleton)
                handler = param.match_type(singleton)

                with self.assertRaises(ValueError):
                    handler.validate(value)

    def test_as_data(self):
        param = SingletonParameter(None)
        handler = param.match_type(None)
        data = handler.as_data(None)

        self.assertIs(data, None)


class SimpleParameterTests(unittest.TestCase):

    def test_match_type_match(self):
        tests = [
            (str, 'spam'),
            (str, String('spam')),
            (int, 10),
            (bool, True),
        ]
        for datatype, value in tests:
            with self.subTest((datatype, value)):
                param = SimpleParameter(datatype, strict=False)
                handler = param.match_type(value)

                self.assertIs(handler.datatype, datatype)

    def test_match_type_no_match(self):
        tests = [
            (int, 'spam'),
            # coercible
            (str, 10),
            (int, 10.0),
            (int, '10'),
            (bool, 1),
            # semi-coercible
            (str, b'spam'),
            (int, 10+0j),
            (int, b'\10'),
        ]
        for datatype, value in tests:
            with self.subTest((datatype, value)):
                param = SimpleParameter(datatype, strict=False)
                handler = param.match_type(value)

                self.assertIs(handler, None)

    def test_match_type_strict_match(self):
        tests = {
            str: 'spam',
            int: 10,
            bool: True,
        }
        for datatype, value in tests.items():
            with self.subTest(datatype):
                param = SimpleParameter(datatype, strict=True)
                handler = param.match_type(value)

                self.assertIs(handler.datatype, datatype)

    def test_match_type_strict_no_match(self):
        tests = {
            str: String('spam'),
            int: Integer(10),
        }
        for datatype, value in tests.items():
            with self.subTest(datatype):
                param = SimpleParameter(datatype, strict=True)
                handler = param.match_type(value)

                self.assertIs(handler, None)

    def test_coerce(self):
        tests = [
            (str, 'spam', 'spam'),
            (str, String('spam'), 'spam'),
            (int, 10, 10),
            (bool, True, True),
            # did not match, but still coercible
            (str, 10, '10'),
            (str, str, "<class 'str'>"),
            (int, 10.0, 10),
            (int, '10', 10),
            (bool, 1, True),
        ]
        for datatype, value, expected in tests:
            with self.subTest((datatype, value)):
                handler = SimpleParameter.HANDLER(datatype)
                coerced = handler.coerce(value)

                self.assertEqual(coerced, expected)

    def test_validate_valid(self):
        tests = {
            str: 'spam',
            int: 10,
            bool: True,
        }
        for datatype, value in tests.items():
            with self.subTest(datatype):
                handler = SimpleParameter.HANDLER(datatype)
                handler.validate(value)

    def test_validate_invalid(self):
        tests = [
            (int, 'spam'),
            # coercible
            (str, String('spam')),
            (str, 10),
            (int, 10.0),
            (int, '10'),
            (bool, 1),
            # semi-coercible
            (str, b'spam'),
            (int, 10+0j),
            (int, b'\10'),
        ]
        for datatype, value in tests:
            with self.subTest((datatype, value)):
                handler = SimpleParameter.HANDLER(datatype)

                with self.assertRaises(ValueError):
                    handler.validate(value)

    def test_as_data(self):
        tests = [
            (str, 'spam'),
            (int, 10),
            (bool, True),
            # did not match, but still coercible
            (str, String('spam')),
            (str, 10),
            (str, str),
            (int, 10.0),
            (int, '10'),
            (bool, 1),
            # semi-coercible
            (str, b'spam'),
            (int, 10+0j),
            (int, b'\10'),
        ]
        for datatype, value in tests:
            with self.subTest((datatype, value)):
                handler = SimpleParameter.HANDLER(datatype)
                data = handler.as_data(value)

                self.assertIs(data, value)


class EnumParameterTests(unittest.TestCase):

    def test_match_type_match(self):
        tests = [
            (str, ('spam', 'eggs'), 'spam'),
            (str, ('spam',), 'spam'),
            (int, (1, 2, 3), 2),
            (bool, (True,), True),
        ]
        for datatype, enum, value in tests:
            with self.subTest((datatype, enum)):
                param = EnumParameter(datatype, enum)
                handler = param.match_type(value)

                self.assertIs(handler.datatype, datatype)

    def test_match_type_no_match(self):
        tests = [
            # enum mismatch
            (str, ('spam', 'eggs'), 'ham'),
            (int, (1, 2, 3), 10),
            # type mismatch
            (int, (1, 2, 3), 'spam'),
            # coercible
            (str, ('spam', 'eggs'), String('spam')),
            (str, ('1', '2', '3'), 2),
            (int, (1, 2, 3), 2.0),
            (int, (1, 2, 3), '2'),
            (bool, (True,), 1),
            # semi-coercible
            (str, ('spam', 'eggs'), b'spam'),
            (int, (1, 2, 3), 2+0j),
            (int, (1, 2, 3), b'\02'),
        ]
        for datatype, enum, value in tests:
            with self.subTest((datatype, enum, value)):
                param = EnumParameter(datatype, enum)
                handler = param.match_type(value)

                self.assertIs(handler, None)

    def test_coerce(self):
        tests = [
            (str, 'spam', 'spam'),
            (int, 10, 10),
            (bool, True, True),
            # did not match, but still coercible
            (str, String('spam'), 'spam'),
            (str, 10, '10'),
            (str, str, "<class 'str'>"),
            (int, 10.0, 10),
            (int, '10', 10),
            (bool, 1, True),
        ]
        for datatype, value, expected in tests:
            with self.subTest((datatype, value)):
                enum = (expected,)
                handler = EnumParameter.HANDLER(datatype, enum)
                coerced = handler.coerce(value)

                self.assertEqual(coerced, expected)

    def test_coerce_enum_mismatch(self):
        enum = ('spam', 'eggs')
        handler = EnumParameter.HANDLER(str, enum)
        coerced = handler.coerce('ham')

        # It still works.
        self.assertEqual(coerced, 'ham')

    def test_validate_valid(self):
        tests = [
            (str, ('spam', 'eggs'), 'spam'),
            (str, ('spam',), 'spam'),
            (int, (1, 2, 3), 2),
            (bool, (True, False), True),
        ]
        for datatype, enum, value in tests:
            with self.subTest((datatype, enum)):
                handler = EnumParameter.HANDLER(datatype, enum)
                handler.validate(value)

    def test_validate_invalid(self):
        tests = [
            # enum mismatch
            (str, ('spam', 'eggs'), 'ham'),
            (int, (1, 2, 3), 10),
            # type mismatch
            (int, (1, 2, 3), 'spam'),
            # coercible
            (str, ('spam', 'eggs'), String('spam')),
            (str, ('1', '2', '3'), 2),
            (int, (1, 2, 3), 2.0),
            (int, (1, 2, 3), '2'),
            (bool, (True,), 1),
            # semi-coercible
            (str, ('spam', 'eggs'), b'spam'),
            (int, (1, 2, 3), 2+0j),
            (int, (1, 2, 3), b'\02'),
        ]
        for datatype, enum, value in tests:
            with self.subTest((datatype, enum, value)):
                handler = EnumParameter.HANDLER(datatype, enum)

                with self.assertRaises(ValueError):
                    handler.validate(value)

    def test_as_data(self):
        tests = [
            (str, ('spam', 'eggs'), 'spam'),
            (str, ('spam',), 'spam'),
            (int, (1, 2, 3), 2),
            (bool, (True,), True),
            # enum mismatch
            (str, ('spam', 'eggs'), 'ham'),
            (int, (1, 2, 3), 10),
            # type mismatch
            (int, (1, 2, 3), 'spam'),
            # coercible
            (str, ('spam', 'eggs'), String('spam')),
            (str, ('1', '2', '3'), 2),
            (int, (1, 2, 3), 2.0),
            (int, (1, 2, 3), '2'),
            (bool, (True,), 1),
            # semi-coercible
            (str, ('spam', 'eggs'), b'spam'),
            (int, (1, 2, 3), 2+0j),
            (int, (1, 2, 3), b'\02'),
        ]
        for datatype, enum, value in tests:
            with self.subTest((datatype, enum, value)):
                handler = EnumParameter.HANDLER(datatype, enum)
                data = handler.as_data(value)

                self.assertIs(data, value)


class UnionParameterTests(unittest.TestCase):

    def test_match_type_all_simple(self):
        tests = [
            'spam',
            10,
            True,
        ]
        datatype = Union(str, int, bool)
        param = UnionParameter(datatype)
        for value in tests:
            with self.subTest(value):
                handler = param.match_type(value)

                self.assertIs(type(handler), SimpleParameter.HANDLER)
                self.assertIs(handler.datatype, type(value))

    def test_match_type_mixed(self):
        datatype = Union(
            str,
            # XXX add dedicated enums
            Enum(int, (1, 2, 3)),
            Basic,
            Array(str),
            Array(int),
            Union(int, bool),
        )
        param = UnionParameter(datatype)

        tests = [
            ('spam', SimpleParameter.HANDLER(str)),
            (2, EnumParameter.HANDLER(int, (1, 2, 3))),
            (BASIC_FULL, ComplexParameter(Basic).match_type(BASIC_FULL)),
            (['spam'], ArrayParameter.HANDLER(Array(str))),
            ([], ArrayParameter.HANDLER(Array(str))),
            ([10], ArrayParameter.HANDLER(Array(int))),
            (10, SimpleParameter.HANDLER(int)),
            (True, SimpleParameter.HANDLER(bool)),
            # no match
            (Integer(2), None),
            ([True], None),
            ({}, None),
        ]
        for value, expected in tests:
            with self.subTest(value):
                handler = param.match_type(value)

                self.assertEqual(handler, expected)

    def test_match_type_catchall(self):
        NOOP = DatatypeHandler(ANY)
        param = UnionParameter(Union(int, str, ANY))
        tests = [
            ('spam', SimpleParameter.HANDLER(str)),
            (10, SimpleParameter.HANDLER(int)),
            # catchall
            (BASIC_FULL, NOOP),
            (['spam'], NOOP),
            (True, NOOP),
            (Integer(2), NOOP),
            ([10], NOOP),
            ({}, NOOP),
        ]
        for value, expected in tests:
            with self.subTest(value):
                handler = param.match_type(value)

                self.assertEqual(handler, expected)

    def test_match_type_no_match(self):
        param = UnionParameter(Union(int, str))
        values = [
            BASIC_FULL,
            ['spam'],
            True,
            Integer(2),
            [10],
            {},
        ]
        for value in values:
            with self.subTest(value):
                handler = param.match_type(value)

                self.assertIs(handler, None)


class ArrayParameterTests(unittest.TestCase):

    def test_match_type_match(self):
        param = ArrayParameter(Array(str))
        expected = ArrayParameter.HANDLER(Array(str))
        values = [
            ['a', 'b', 'c'],
            [],
        ]
        for value in values:
            with self.subTest(value):
                handler = param.match_type(value)

                self.assertEqual(handler, expected)

    def test_match_type_no_match(self):
        param = ArrayParameter(Array(str))
        values = [
            ['a', 1, 'c'],
            ('a', 'b', 'c'),
            'spam',
        ]
        for value in values:
            with self.subTest(value):
                handler = param.match_type(value)

                self.assertIs(handler, None)

    def test_coerce_simple(self):
        param = ArrayParameter(Array(str))
        values = [
            ['a', 'b', 'c'],
            [],
        ]
        for value in values:
            with self.subTest(value):
                handler = param.match_type(value)
                coerced = handler.coerce(value)

                self.assertEqual(coerced, value)

    def test_coerce_complicated(self):
        param = ArrayParameter(Array(Union(str, Basic)))
        value = [
            'a',
            BASIC_FULL,
            'c',
        ]
        handler = param.match_type(value)
        coerced = handler.coerce(value)

        self.assertEqual(coerced, [
            'a',
            Basic(name='spam', value='eggs'),
            'c',
        ])

    def test_validate(self):
        param = ArrayParameter(Array(str))
        handler = param.match_type(['a', 'b', 'c'])
        handler.validate(['a', 'b', 'c'])

    def test_as_data_simple(self):
        param = ArrayParameter(Array(str))
        handler = param.match_type(['a', 'b', 'c'])
        data = handler.as_data(['a', 'b', 'c'])

        self.assertEqual(data, ['a', 'b', 'c'])

    def test_as_data_complicated(self):
        param = ArrayParameter(Array(Union(str, Basic)))
        value = [
            'a',
            BASIC_FULL,
            'c',
        ]
        handler = param.match_type(value)
        data = handler.as_data([
            'a',
            Basic(name='spam', value='eggs'),
            'c',
        ])

        self.assertEqual(data, value)


class ComplexParameterTests(unittest.TestCase):

    def test_match_type_none_missing(self):
        fields = Fields(*FIELDS_BASIC)
        param = ComplexParameter(fields)
        handler = param.match_type(BASIC_FULL)

        self.assertIs(type(handler), ComplexParameter.HANDLER)
        self.assertEqual(handler.datatype.FIELDS, fields)

    def test_match_type_missing_optional(self):
        fields = Fields(
            Field('name'),
            Field.START_OPTIONAL,
            Field('value'),
        )
        param = ComplexParameter(fields)
        handler = param.match_type({'name': 'spam'})

        self.assertIs(type(handler), ComplexParameter.HANDLER)
        self.assertEqual(handler.datatype.FIELDS, fields)
        self.assertNotIn('value', handler.handlers)

    def test_coerce(self):
        handler = ComplexParameter.HANDLER(Basic)
        coerced = handler.coerce(BASIC_FULL)

        self.assertEqual(coerced, Basic(**BASIC_FULL))

    def test_validate(self):
        handler = ComplexParameter.HANDLER(Basic)
        handler.coerce(BASIC_FULL)
        coerced = Basic(**BASIC_FULL)
        handler.validate(coerced)

    def test_as_data(self):
        handler = ComplexParameter.HANDLER(Basic)
        handler.coerce(BASIC_FULL)
        coerced = Basic(**BASIC_FULL)
        data = handler.as_data(coerced)

        self.assertEqual(data, BASIC_FULL)
