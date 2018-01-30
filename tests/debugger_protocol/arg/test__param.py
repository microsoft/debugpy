from types import SimpleNamespace
import unittest

from debugger_protocol.arg import NOT_SET
from debugger_protocol.arg._param import Parameter, ParameterImplBase, Arg

from tests.helpers.stub import Stub


class FakeImpl(ParameterImplBase):

    def __init__(self, stub=None):
        super().__init__()
        self._bind_attrs(
            stub=stub or Stub(),
            returns=SimpleNamespace(
                match_type=None,
                missing=None,
                coerce=None,
                as_data=None,
            ),
        )

    def match_type(self, raw):
        self.stub.add_call('match_type', raw)
        self.stub.maybe_raise()
        return self.returns.match_type

    def missing(self, raw):
        self.stub.add_call('missing', raw)
        self.stub.maybe_raise()
        return self.returns.missing

    def coerce(self, raw):
        self.stub.add_call('coerce', raw)
        self.stub.maybe_raise()
        return self.returns.coerce

    def validate(self, coerced):
        self.stub.add_call('validate', coerced)
        self.stub.maybe_raise()

    def as_data(self, coerced):
        self.stub.add_call('as_data', coerced)
        self.stub.maybe_raise()
        return self.returns.as_data


class ParameterTests(unittest.TestCase):

    def setUp(self):
        super().setUp()
        self.stub = Stub()
        self.impl = FakeImpl(self.stub)

    def test_bad_impl(self):
        with self.assertRaises(TypeError):
            Parameter(None)
        with self.assertRaises(TypeError):
            Parameter(str)

    def test_bind_matched(self):
        self.impl.returns.match_type = self.impl
        param = Parameter(self.impl)
        arg = param.bind('spam')

        self.assertEqual(arg, Arg(param, 'spam'))
        self.assertEqual(self.stub.calls, [
            ('match_type', ('spam',), {}),
        ])

    def test_bind_no_match(self):
        self.impl.returns.match_type = None
        param = Parameter(self.impl)

        with self.assertRaises(TypeError):
            param.bind('spam')
        self.assertEqual(self.stub.calls, [
            ('match_type', ('spam',), {}),
        ])

    def test_match_type_no_match(self):
        self.impl.returns.match_type = None
        param = Parameter(self.impl)
        matched = param.match_type('spam')

        self.assertIs(matched, None)
        self.assertEqual(self.stub.calls, [
            ('match_type', ('spam',), {}),
        ])

    def test_match_type_param(self):
        other = Parameter(ParameterImplBase(str))
        self.impl.returns.match_type = other
        param = Parameter(self.impl)
        matched = param.match_type('spam')

        self.assertIs(matched, other)
        self.assertNotEqual(matched, param)
        self.assertEqual(self.stub.calls, [
            ('match_type', ('spam',), {}),
        ])

    def test_match_type_impl_noop(self):
        self.impl.returns.match_type = self.impl
        param = Parameter(self.impl)
        matched = param.match_type('spam')

        self.assertIs(matched, param)
        self.assertEqual(self.stub.calls, [
            ('match_type', ('spam',), {}),
        ])

    def test_match_type_impl_wrap(self):
        other = ParameterImplBase(str)
        self.impl.returns.match_type = other
        param = Parameter(self.impl)
        matched = param.match_type('spam')

        self.assertNotEqual(matched, param)
        self.assertIs(matched._impl, other)
        self.assertEqual(self.stub.calls, [
            ('match_type', ('spam',), {}),
        ])

    def test_missing(self):
        self.impl.returns.missing = False
        param = Parameter(self.impl)
        missing = param.missing('spam')

        self.assertFalse(missing)
        self.assertEqual(self.stub.calls, [
            ('missing', ('spam',), {}),
        ])

    def test_coerce(self):
        self.impl.returns.coerce = 'spam'
        param = Parameter(self.impl)
        coerced = param.coerce('spam')

        self.assertEqual(coerced, 'spam')
        self.assertEqual(self.stub.calls, [
            ('coerce', ('spam',), {}),
        ])

    def test_validate_use_impl(self):
        param = Parameter(self.impl)
        param.validate('spam')

        self.assertEqual(self.stub.calls, [
            ('validate', ('spam',), {}),
        ])

    def test_validate_use_coerced(self):
        other = FakeImpl()
        arg = Arg(Parameter(other), 'spam', israw=False)
        param = Parameter(self.impl)
        param.validate(arg)

        self.assertEqual(self.stub.calls, [])
        self.assertEqual(other.stub.calls, [
            ('validate', ('spam',), {}),
        ])

    def test_as_data_use_impl(self):
        self.impl.returns.as_data = 'spam'
        param = Parameter(self.impl)
        data = param.as_data('spam')

        self.assertEqual(data, 'spam')
        self.assertEqual(self.stub.calls, [
            ('as_data', ('spam',), {}),
        ])

    def test_as_data_use_coerced(self):
        other = FakeImpl()
        arg = Arg(Parameter(other), 'spam', israw=False)
        other.returns.as_data = 'spam'
        param = Parameter(self.impl)
        data = param.as_data(arg)

        self.assertEqual(data, 'spam')
        self.assertEqual(self.stub.calls, [])
        self.assertEqual(other.stub.calls, [
            ('validate', ('spam',), {}),
            ('as_data', ('spam',), {}),
        ])


class ParameterImplBaseTests(unittest.TestCase):

    def test_defaults(self):
        impl = ParameterImplBase()

        self.assertIs(impl.datatype, NOT_SET)

    def test_match_type(self):
        impl = ParameterImplBase()
        param = impl.match_type('spam')

        self.assertIs(param, impl)

    def test_missing(self):
        impl = ParameterImplBase()
        missing = impl.missing('spam')

        self.assertFalse(missing)

    def test_coerce(self):
        values = [
            (str, 'spam'),
            (int, 10),
            (str, 10),
            (int, '10'),
        ]
        for datatype, value in values:
            with self.subTest(value):
                impl = ParameterImplBase(datatype)
                coerced = impl.coerce(value)

                self.assertEqual(coerced, value)

    def test_validate(self):
        impl = ParameterImplBase(str)
        impl.validate('spam')

    def test_as_data(self):
        impl = ParameterImplBase(str)
        data = impl.as_data('spam')

        self.assertEqual(data, 'spam')


class ArgTests(unittest.TestCase):

    def setUp(self):
        super().setUp()
        self.stub = Stub()
        self.impl = FakeImpl(self.stub)
        self.param = Parameter(self.impl)

    def test_raw_valid(self):
        self.impl.returns.coerce = 'eggs'
        arg = Arg(self.param, 'spam')
        raw = arg.raw

        self.assertEqual(raw, 'spam')
        self.assertEqual(self.stub.calls, [
            ('coerce', ('spam',), {}),
            ('validate', ('eggs',), {}),
        ])

    def test_raw_invalid(self):
        self.impl.returns.coerce = 'eggs'
        self.stub.set_exceptions(
            None,
            ValueError('oops'),
        )
        arg = Arg(self.param, 'spam')

        with self.assertRaises(ValueError):
            arg.raw
        self.assertEqual(self.stub.calls, [
            ('coerce', ('spam',), {}),
            ('validate', ('eggs',), {}),
        ])

    def test_raw_generated(self):
        self.impl.returns.as_data = 'spam'
        arg = Arg(self.param, 'eggs', israw=False)
        raw = arg.raw

        self.assertEqual(raw, 'spam')
        self.assertEqual(self.stub.calls, [
            ('validate', ('eggs',), {}),
            ('as_data', ('eggs',), {}),
        ])

    def test_value_valid(self):
        arg = Arg(self.param, 'eggs', israw=False)
        value = arg.value

        self.assertEqual(value, 'eggs')
        self.assertEqual(self.stub.calls, [
            ('validate', ('eggs',), {}),
        ])

    def test_value_invalid(self):
        self.stub.set_exceptions(
            ValueError('oops'),
        )
        arg = Arg(self.param, 'eggs', israw=False)

        with self.assertRaises(ValueError):
            arg.value
        self.assertEqual(self.stub.calls, [
            ('validate', ('eggs',), {}),
        ])

    def test_value_generated(self):
        self.impl.returns.coerce = 'eggs'
        arg = Arg(self.param, 'spam')
        value = arg.value

        self.assertEqual(value, 'eggs')
        self.assertEqual(self.stub.calls, [
            ('coerce', ('spam',), {}),
            ('validate', ('eggs',), {}),
        ])

    def test_coerce(self):
        self.impl.returns.coerce = 'eggs'
        arg = Arg(self.param, 'spam')
        value = arg.coerce()

        self.assertEqual(value, 'eggs')
        self.assertEqual(self.stub.calls, [
            ('coerce', ('spam',), {}),
        ])

    def test_validate_okay(self):
        self.impl.returns.coerce = 'eggs'
        arg = Arg(self.param, 'spam')
        arg.validate()

        self.assertEqual(self.stub.calls, [
            ('coerce', ('spam',), {}),
            ('validate', ('eggs',), {}),
        ])

    def test_validate_invalid(self):
        self.stub.set_exceptions(
            None,
            ValueError('oops'),
        )
        self.impl.returns.coerce = 'eggs'
        arg = Arg(self.param, 'spam')

        with self.assertRaises(ValueError):
            arg.validate()
        self.assertEqual(self.stub.calls, [
            ('coerce', ('spam',), {}),
            ('validate', ('eggs',), {}),
        ])

    def test_as_data(self):
        self.impl.returns.as_data = 'spam'
        arg = Arg(self.param, 'eggs', israw=False)
        data = arg.as_data()

        self.assertEqual(data, 'spam')
        self.assertEqual(self.stub.calls, [
            ('validate', ('eggs',), {}),
            ('as_data', ('eggs',), {}),
        ])
