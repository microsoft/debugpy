import itertools
import unittest

from debugger_protocol.arg._common import ANY
from debugger_protocol.arg._datatype import FieldsNamespace
from debugger_protocol.arg._decl import Union, Array, Field, Fields
from debugger_protocol.arg._param import Parameter, DatatypeHandler, Arg

from ._common import (
    BASIC_FULL, BASIC_MIN, Basic,
    FIELDS_EXTENDED, EXTENDED_FULL, EXTENDED_MIN)


class FieldsNamespaceTests(unittest.TestCase):

    def test_traverse_noop(self):
        fields = [
            Field('spam'),
            Field('ham'),
            Field('eggs'),
        ]

        class Spam(FieldsNamespace):
            FIELDS = Fields(*fields)

        calls = []
        op = (lambda dt: calls.append(dt) or dt)
        transformed = Spam.traverse(op)

        self.assertIs(transformed, Spam)
        self.assertIs(transformed.FIELDS, Spam.FIELDS)
        for i, field in enumerate(Spam.FIELDS):
            self.assertIs(field, fields[i])
        self.assertCountEqual(calls, [
            # Note that it did not recurse into the fields.
            Field('spam'),
            Field('ham'),
            Field('eggs'),
        ])

    def test_traverse_unnormalized(self):
        fields = [
            Field('spam'),
            Field('ham'),
            Field('eggs'),
        ]

        class Spam(FieldsNamespace):
            FIELDS = fields

        calls = []
        op = (lambda dt: calls.append(dt) or dt)
        transformed = Spam.traverse(op)

        self.assertIs(transformed, Spam)
        self.assertIsInstance(transformed.FIELDS, Fields)
        for i, field in enumerate(Spam.FIELDS):
            self.assertIs(field, fields[i])
        self.assertCountEqual(calls, [
            Field('spam'),
            Field('ham'),
            Field('eggs'),
        ])

    def test_traverse_changed(self):
        class Spam(FieldsNamespace):
            FIELDS = Fields(
                Field('spam', ANY),
                Field('eggs', None),
            )

        calls = []
        op = (lambda dt: calls.append(dt) or Field(dt.name, str))
        transformed = Spam.traverse(op)

        self.assertIs(transformed, Spam)
        self.assertEqual(transformed.FIELDS, Fields(
            Field('spam', str),
            Field('eggs', str),
        ))
        self.assertEqual(calls, [
            Field('spam', ANY),
            Field('eggs', None),
        ])

    def test_normalize_without_ops(self):
        fieldlist = [
            Field('spam'),
            Field('ham'),
            Field('eggs'),
        ]
        fields = Fields(*fieldlist)

        class Spam(FieldsNamespace):
            FIELDS = fields

        Spam.normalize()

        self.assertIs(Spam.FIELDS, fields)
        for i, field in enumerate(Spam.FIELDS):
            self.assertIs(field, fieldlist[i])

    def test_normalize_unnormalized(self):
        fieldlist = [
            Field('spam'),
            Field('ham'),
            Field('eggs'),
        ]

        class Spam(FieldsNamespace):
            FIELDS = fieldlist

        Spam.normalize()

        self.assertIsInstance(Spam.FIELDS, Fields)
        for i, field in enumerate(Spam.FIELDS):
            self.assertIs(field, fieldlist[i])

    def test_normalize_with_ops_noop(self):
        fieldlist = [
            Field('spam'),
            Field('ham', int),
            Field('eggs', Array(ANY)),
        ]
        fields = Fields(*fieldlist)

        class Spam(FieldsNamespace):
            FIELDS = fields

        calls = []
        op1 = (lambda dt: calls.append((op1, dt)) or dt)
        op2 = (lambda dt: calls.append((op2, dt)) or dt)
        Spam.normalize(op1, op2)

        self.assertIs(Spam.FIELDS, fields)
        for i, field in enumerate(Spam.FIELDS):
            self.assertIs(field, fieldlist[i])
        self.maxDiff = None
        self.assertEqual(calls, [
            (op1, fields),
            (op1, Field('spam')),
            (op1, str),
            (op1, Field('ham', int)),
            (op1, int),
            (op1, Field('eggs', Array(ANY))),
            (op1, Array(ANY)),
            (op1, ANY),

            (op2, fields),
            (op2, Field('spam')),
            (op2, str),
            (op2, Field('ham', int)),
            (op2, int),
            (op2, Field('eggs', Array(ANY))),
            (op2, Array(ANY)),
            (op2, ANY),
        ])

    def test_normalize_with_op_changed(self):
        class Spam(FieldsNamespace):
            FIELDS = Fields(
                Field('spam', Array(ANY)),
            )

        op = (lambda dt: int if dt is ANY else dt)
        Spam.normalize(op)

        self.assertEqual(Spam.FIELDS, Fields(
            Field('spam', Array(int)),
        ))

    def test_normalize_declarative(self):
        class Spam(FieldsNamespace):
            FIELDS = [
                Field('a'),
                Field('b', bool),
                Field.START_OPTIONAL,
                Field('c', {int, str}),
                Field('d', [int]),
                Field('e', ANY),
                Field('f', '<ref>'),
            ]

        class Ham(FieldsNamespace):
            FIELDS = [
                Field('w', Spam),
                Field('x', int),
                Field('y', frozenset({int, str})),
                Field('z', (int,)),
            ]

        class Eggs(FieldsNamespace):
            FIELDS = [
                Field('b', [Ham]),
                Field('x', [{str, ('<ref>',)}], optional=True),
                Field('d', {Spam, '<ref>'}, optional=True),
            ]

        Eggs.normalize()

        self.assertEqual(Spam.FIELDS, Fields(
            Field('a'),
            Field('b', bool),
            Field('c', Union(int, str), optional=True),
            Field('d', Array(int), optional=True),
            Field('e', ANY, optional=True),
            Field('f', Spam, optional=True),
        ))
        self.assertEqual(Ham.FIELDS, Fields(
            Field('w', Spam),
            Field('x', int),
            Field('y', Union(int, str)),
            Field('z', Array(int)),
        ))
        self.assertEqual(Eggs.FIELDS, Fields(
            Field('b', Array(Ham)),
            Field('x',
                  Array(Union.unordered(str, Array(Eggs))),
                  optional=True),
            Field('d', Union.unordered(Spam, Eggs), optional=True),
        ))

    def test_normalize_missing(self):
        with self.assertRaises(TypeError):
            FieldsNamespace.normalize()

    #######

    def test_bind_no_param(self):
        class Spam(FieldsNamespace):
            FIELDS = [
                Field('a'),
            ]

        arg = Spam.bind({'a': 'x'})

        self.assertIsInstance(arg, Spam)
        self.assertEqual(arg, Spam(a='x'))

    def test_bind_with_param_obj(self):
        class Param(Parameter):
            HANDLER = DatatypeHandler(ANY)
            match_type = (lambda self, raw: self.HANDLER)

        class Spam(FieldsNamespace):
            PARAM = Param(ANY)
            FIELDS = [
                Field('a'),
            ]

        arg = Spam.bind({'a': 'x'})

        self.assertIsInstance(arg, Arg)
        self.assertEqual(arg, Arg(Param(ANY), {'a': 'x'}))

    def test_bind_with_param_type(self):
        class Param(Parameter):
            HANDLER = DatatypeHandler(ANY)
            match_type = (lambda self, raw: self.HANDLER)

        class Spam(FieldsNamespace):
            PARAM_TYPE = Param
            FIELDS = [
                Field('a'),
            ]

        arg = Spam.bind({'a': 'x'})

        self.assertIsInstance(arg, Arg)
        self.assertEqual(arg, Arg(Param(Spam.FIELDS), {'a': 'x'}))

    def test_bind_already_bound(self):
        class Spam(FieldsNamespace):
            FIELDS = [
                Field('a'),
            ]

        spam = Spam(a='x')
        arg = Spam.bind(spam)

        self.assertIs(arg, spam)

    #######

    def test_fields_full(self):
        class Spam(FieldsNamespace):
            FIELDS = FIELDS_EXTENDED

        spam = Spam(**EXTENDED_FULL)
        ns = vars(spam)
        del ns['_validators']
        del ns['_serializers']

        self.assertEqual(ns, {
            'name': 'spam',
            'valid': True,
            'id': 10,
            'value': None,
            'x': Basic(**BASIC_FULL),
            'y': 11,
            'z': [
                Basic(**BASIC_FULL),
                Basic(**BASIC_MIN),
            ],
        })

    def test_fields_min(self):
        class Spam(FieldsNamespace):
            FIELDS = FIELDS_EXTENDED

        spam = Spam(**EXTENDED_MIN)
        ns = vars(spam)
        del ns['_validators']
        del ns['_serializers']

        self.assertEqual(ns, {
            'name': 'spam',
            'id': 10,
        })

    def test_no_fields(self):
        with self.assertRaises(TypeError):
            FieldsNamespace(
                x='spam',
                y=42,
                z=None,
            )

    def test_attrs(self):
        ns = Basic(name='<name>', value='<value>')

        self.assertEqual(ns.name, '<name>')
        self.assertEqual(ns.value, '<value>')

    def test_equality(self):
        ns1 = Basic(name='<name>', value='<value>')
        ns2 = Basic(name='<name>', value='<value>')

        self.assertTrue(ns1 == ns1)
        self.assertTrue(ns1 == ns2)

    def test_inequality(self):
        p = [Basic(name=n, value=v)
             for n in ['<>', '<name>']
             for v in ['<>', '<value>']]
        for basic1, basic2 in itertools.combinations(p, 2):
            with self.subTest((basic1, basic2)):
                self.assertTrue(basic1 != basic2)

    @unittest.skip('not ready')
    def test_validate(self):
        # TODO: finish
        raise NotImplementedError

    def test_as_data(self):
        class Spam(FieldsNamespace):
            FIELDS = FIELDS_EXTENDED

        spam = Spam(**EXTENDED_FULL)
        sdata = spam.as_data()
        basic = Basic(**BASIC_FULL)
        bdata = basic.as_data()

        self.assertEqual(sdata, EXTENDED_FULL)
        self.assertEqual(bdata, BASIC_FULL)
