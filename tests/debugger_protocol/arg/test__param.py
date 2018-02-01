from types import SimpleNamespace
import unittest

from debugger_protocol.arg._param import Parameter, DatatypeHandler, Arg

from tests.helpers.stub import Stub


class FakeHandler(DatatypeHandler):

    def __init__(self, datatype=str, stub=None):
        super().__init__(datatype)
        self.stub = stub or Stub()
        self.returns = SimpleNamespace(
            coerce=None,
            as_data=None,
        )

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
        self.handler = FakeHandler(self.stub)

    def test_bind_matched(self):
        param = Parameter(str, self.handler)
        arg = param.bind('spam')

        self.assertEqual(arg, Arg(param, 'spam', self.handler))
        self.assertEqual(self.stub.calls, [])

    def test_bind_no_match(self):
        param = Parameter(str)

        arg = param.bind('spam')
        self.assertIs(arg, None)
        self.assertEqual(self.stub.calls, [])

    def test_match_type_no_match(self):
        param = Parameter(str)
        matched = param.match_type('spam')

        self.assertIs(matched, None)
        self.assertEqual(self.stub.calls, [])

    def test_match_type_matched(self):
        param = Parameter(str, self.handler)
        matched = param.match_type('spam')

        self.assertIs(matched, self.handler)
        self.assertEqual(self.stub.calls, [])


class DatatypeHandlerTests(unittest.TestCase):

    def test_coerce(self):
        handler = DatatypeHandler(str)
        coerced = handler.coerce('spam')

        self.assertEqual(coerced, 'spam')

    def test_validate(self):
        handler = DatatypeHandler(str)
        handler.validate('spam')

    def test_as_data(self):
        handler = DatatypeHandler(str)
        data = handler.as_data('spam')

        self.assertEqual(data, 'spam')


class ArgTests(unittest.TestCase):

    def setUp(self):
        super().setUp()
        self.stub = Stub()
        self.handler = FakeHandler(str, self.stub)
        self.param = Parameter(str, self.handler)

    def test_raw_valid(self):
        self.handler.returns.coerce = 'eggs'
        arg = Arg(self.param, 'spam', self.handler)
        raw = arg.raw

        self.assertEqual(raw, 'spam')
        self.assertEqual(self.stub.calls, [
            ('coerce', ('spam',), {}),
            ('validate', ('eggs',), {}),
        ])

    def test_raw_invalid(self):
        self.handler.returns.coerce = 'eggs'
        self.stub.set_exceptions(
            None,
            ValueError('oops'),
        )
        arg = Arg(self.param, 'spam', self.handler)

        with self.assertRaises(ValueError):
            arg.raw
        self.assertEqual(self.stub.calls, [
            ('coerce', ('spam',), {}),
            ('validate', ('eggs',), {}),
        ])

    def test_raw_generated(self):
        self.handler.returns.as_data = 'spam'
        arg = Arg(self.param, 'eggs', self.handler, israw=False)
        raw = arg.raw

        self.assertEqual(raw, 'spam')
        self.assertEqual(self.stub.calls, [
            ('validate', ('eggs',), {}),
            ('as_data', ('eggs',), {}),
        ])

    def test_value_valid(self):
        arg = Arg(self.param, 'eggs', self.handler, israw=False)
        value = arg.value

        self.assertEqual(value, 'eggs')
        self.assertEqual(self.stub.calls, [
            ('validate', ('eggs',), {}),
        ])

    def test_value_invalid(self):
        self.stub.set_exceptions(
            ValueError('oops'),
        )
        arg = Arg(self.param, 'eggs', self.handler, israw=False)

        with self.assertRaises(ValueError):
            arg.value
        self.assertEqual(self.stub.calls, [
            ('validate', ('eggs',), {}),
        ])

    def test_value_generated(self):
        self.handler.returns.coerce = 'eggs'
        arg = Arg(self.param, 'spam', self.handler)
        value = arg.value

        self.assertEqual(value, 'eggs')
        self.assertEqual(self.stub.calls, [
            ('coerce', ('spam',), {}),
            ('validate', ('eggs',), {}),
        ])

    def test_coerce(self):
        self.handler.returns.coerce = 'eggs'
        arg = Arg(self.param, 'spam', self.handler)
        value = arg.coerce()

        self.assertEqual(value, 'eggs')
        self.assertEqual(self.stub.calls, [
            ('coerce', ('spam',), {}),
        ])

    def test_validate_okay(self):
        self.handler.returns.coerce = 'eggs'
        arg = Arg(self.param, 'spam', self.handler)
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
        self.handler.returns.coerce = 'eggs'
        arg = Arg(self.param, 'spam', self.handler)

        with self.assertRaises(ValueError):
            arg.validate()
        self.assertEqual(self.stub.calls, [
            ('coerce', ('spam',), {}),
            ('validate', ('eggs',), {}),
        ])

    def test_validate_use_coerced(self):
        handler = FakeHandler()
        other = Arg(Parameter(str, handler), 'spam', handler, israw=False)
        arg = Arg(Parameter(str, self.handler), other, self.handler,
                  israw=False)
        arg.validate()

        self.assertEqual(self.stub.calls, [])
        self.assertEqual(handler.stub.calls, [
            ('validate', ('spam',), {}),
        ])

    def test_as_data_use_handler(self):
        self.handler.returns.as_data = 'spam'
        arg = Arg(self.param, 'eggs', self.handler, israw=False)
        data = arg.as_data()

        self.assertEqual(data, 'spam')
        self.assertEqual(self.stub.calls, [
            ('validate', ('eggs',), {}),
            ('as_data', ('eggs',), {}),
        ])

    def test_as_data_use_coerced(self):
        handler = FakeHandler()
        other = Arg(Parameter(str, handler), 'spam', handler, israw=False)
        handler.returns.as_data = 'spam'
        arg = Arg(Parameter(str, self.handler), other, self.handler,
                  israw=False)
        data = arg.as_data(other)

        self.assertEqual(data, 'spam')
        self.assertEqual(self.stub.calls, [])
        self.assertEqual(handler.stub.calls, [
            ('validate', ('spam',), {}),
            ('as_data', ('spam',), {}),
        ])
