import unittest

from debugger_protocol.arg import FieldsNamespace, Field
from debugger_protocol.messages import register
from debugger_protocol.messages.message import (
        ProtocolMessage, Request, Response, Event)


@register
class DummyRequest(object):
    TYPE = 'request'
    TYPE_KEY = 'command'
    COMMAND = '...'


@register
class DummyResponse(object):
    TYPE = 'response'
    TYPE_KEY = 'command'
    COMMAND = '...'


@register
class DummyEvent(object):
    TYPE = 'event'
    TYPE_KEY = 'event'
    EVENT = '...'


class FakeMsg(ProtocolMessage):

    SEQ = 0

    @classmethod
    def _next_reqid(cls):
        return cls.SEQ


class ProtocolMessageTests(unittest.TestCase):

    def test_from_data(self):
        data = {
            'type': 'event',
            'seq': 10,
        }
        msg = ProtocolMessage.from_data(**data)

        self.assertEqual(msg.type, 'event')
        self.assertEqual(msg.seq, 10)

    def test_defaults(self):  # no args
        class Spam(FakeMsg):
            SEQ = 10
            TYPE = 'event'

        msg = Spam()

        self.assertEqual(msg.type, 'event')
        self.assertEqual(msg.seq, 10)

    def test_all_args(self):
        msg = ProtocolMessage(10, type='event')

        self.assertEqual(msg.type, 'event')
        self.assertEqual(msg.seq, 10)

    def test_coercion_seq(self):
        msg = ProtocolMessage('10', type='event')

        self.assertEqual(msg.seq, 10)

    def test_validation(self):
        # type

        with self.assertRaises(TypeError):
            ProtocolMessage(type=None)
        with self.assertRaises(ValueError):
            ProtocolMessage(type='spam')

        class Other(ProtocolMessage):
            TYPE = 'spam'

        with self.assertRaises(ValueError):
            Other(type='event')

        # seq

        with self.assertRaises(TypeError):
            ProtocolMessage(None, type='event')
        with self.assertRaises(ValueError):
            ProtocolMessage(-1, type='event')

    def test_readonly(self):
        msg = ProtocolMessage(10, type='event')

        with self.assertRaises(AttributeError):
            msg.seq = 11
        with self.assertRaises(AttributeError):
            msg.type = 'event'
        with self.assertRaises(AttributeError):
            msg.spam = object()
        with self.assertRaises(AttributeError):
            del msg.seq

    def test_repr(self):
        msg = ProtocolMessage(10, type='event')
        result = repr(msg)

        self.assertEqual(result, "ProtocolMessage(type='event', seq=10)")

    def test_repr_subclass(self):
        class Eventish(ProtocolMessage):
            TYPE = 'event'

        msg = Eventish(10)
        result = repr(msg)

        self.assertEqual(result, 'Eventish(seq=10)')

    def test_as_data(self):
        msg = ProtocolMessage(10, type='event')
        data = msg.as_data()

        self.assertEqual(data, {
            'type': 'event',
            'seq': 10,
        })


class RequestTests(unittest.TestCase):

    def test_from_data_without_arguments(self):
        data = {
            'type': 'request',
            'seq': 10,
            'command': 'spam',
        }
        msg = Request.from_data(**data)

        self.assertEqual(msg.type, 'request')
        self.assertEqual(msg.seq, 10)
        self.assertEqual(msg.command, 'spam')
        self.assertIsNone(msg.arguments)

    def test_from_data_with_arguments(self):
        class Spam(Request):
            class ARGUMENTS(FieldsNamespace):
                FIELDS = [
                    Field('a'),
                ]

        data = {
            'type': 'request',
            'seq': 10,
            'command': 'spam',
            'arguments': {'a': 'b'},
        }
        #msg = Request.from_data(**data)
        msg = Spam.from_data(**data)

        self.assertEqual(msg.type, 'request')
        self.assertEqual(msg.seq, 10)
        self.assertEqual(msg.command, 'spam')
        self.assertEqual(msg.arguments, {'a': 'b'})

    def test_defaults(self):
        class Spam(Request, FakeMsg):
            SEQ = 10
            COMMAND = 'spam'

        msg = Spam()

        self.assertEqual(msg.type, 'request')
        self.assertEqual(msg.seq, 10)
        self.assertEqual(msg.command, 'spam')
        self.assertIsNone(msg.arguments)

    def test_all_args(self):
        class Spam(Request):
            class ARGUMENTS(FieldsNamespace):
                FIELDS = [
                    Field('a'),
                ]

        args = {'a': 'b'}
        msg = Spam(arguments=args, command='spam', seq=10)

        self.assertEqual(msg.type, 'request')
        self.assertEqual(msg.seq, 10)
        self.assertEqual(msg.command, 'spam')
        self.assertEqual(msg.arguments, args)

    def test_no_arguments_not_required(self):
        class Spam(Request):
            COMMAND = 'spam'
            ARGUMENTS = True
            ARGUMENTS_REQUIRED = False

        msg = Spam()

        self.assertIsNone(msg.arguments)

    def test_no_args(self):
        with self.assertRaises(TypeError):
            Request()

    def test_coercion_arguments(self):
        class Spam(Request):
            COMMAND = 'spam'
            class ARGUMENTS(FieldsNamespace):  # noqa
                FIELDS = [
                    Field('a'),
                ]

        args = [('a', 'b')]
        msg = Spam(args)

        self.assertEqual(msg.arguments, {'a': 'b'})

        with self.assertRaises(TypeError):
            Spam(command='spam', arguments=11)

    def test_validation(self):
        with self.assertRaises(TypeError):
            Request()

        # command

        class Other1(Request):
            COMMAND = 'eggs'

        with self.assertRaises(ValueError):
            # command doesn't match
            Other1(arguments=10, command='spam')

        # arguments

        with self.assertRaises(TypeError):
            # unexpected arguments
            Request(arguments=10, command='spam')

        class Other2(Request):
            COMMAND = 'spam'
            ARGUMENTS = int

        with self.assertRaises(ValueError):
            # missing arguments (implicitly required)
            Other2(command='eggs')

        class Other3(Request):
            COMMAND = 'eggs'
            ARGUMENTS = int
            ARGUMENTS_REQUIRED = True

        with self.assertRaises(ValueError):
            # missing arguments (explicitly required)
            Other2(command='eggs')

    def test_repr_minimal(self):
        msg = Request(command='spam', seq=10)
        result = repr(msg)

        self.assertEqual(result, "Request(command='spam', seq=10)")

    def test_repr_full(self):
        msg = Request(command='spam', seq=10)
        result = repr(msg)

        self.assertEqual(result, "Request(command='spam', seq=10)")

    def test_repr_subclass_minimal(self):
        class SpamRequest(Request):
            COMMAND = 'spam'

        msg = SpamRequest(seq=10)
        result = repr(msg)

        self.assertEqual(result, "SpamRequest(seq=10)")

    def test_repr_subclass_full(self):
        class SpamRequest(Request):
            COMMAND = 'spam'
            class ARGUMENTS(FieldsNamespace):  # noqa
                FIELDS = [
                    Field('a'),
                ]

        msg = SpamRequest(arguments={'a': 'b'}, seq=10)
        result = repr(msg)

        self.assertEqual(result,
                         "SpamRequest(arguments=ARGUMENTS(a='b'), seq=10)")

    def test_as_data_minimal(self):
        msg = Request(command='spam', seq=10)
        data = msg.as_data()

        self.assertEqual(data, {
            'type': 'request',
            'seq': 10,
            'command': 'spam',
        })

    def test_as_data_full(self):
        class Spam(Request):
            COMMAND = 'spam'
            class ARGUMENTS(FieldsNamespace):  # noqa
                FIELDS = [
                    Field('a'),
                ]

        msg = Spam(arguments={'a': 'b'}, seq=10)
        data = msg.as_data()

        self.assertEqual(data, {
            'type': 'request',
            'seq': 10,
            'command': 'spam',
            'arguments': {'a': 'b'},
        })


class ResponseTests(unittest.TestCase):

    def test_from_data_without_body(self):
        data = {
            'type': 'response',
            'seq': 10,
            'command': 'spam',
            'request_seq': 9,
            'success': True,
        }
        msg = Response.from_data(**data)

        self.assertEqual(msg.type, 'response')
        self.assertEqual(msg.seq, 10)
        self.assertEqual(msg.command, 'spam')
        self.assertEqual(msg.request_seq, 9)
        self.assertTrue(msg.success)
        self.assertIsNone(msg.body)
        self.assertIsNone(msg.message)

    def test_from_data_with_body(self):
        class Spam(Response):
            class BODY(FieldsNamespace):
                FIELDS = [
                    Field('a'),
                ]

        data = {
            'type': 'response',
            'seq': 10,
            'command': 'spam',
            'request_seq': 9,
            'success': True,
            'body': {'a': 'b'},
        }
        msg = Spam.from_data(**data)

        self.assertEqual(msg.type, 'response')
        self.assertEqual(msg.seq, 10)
        self.assertEqual(msg.command, 'spam')
        self.assertEqual(msg.request_seq, 9)
        self.assertTrue(msg.success)
        self.assertEqual(msg.body, {'a': 'b'})
        self.assertIsNone(msg.message)

    def test_from_data_error_without_body(self):
        data = {
            'type': 'response',
            'seq': 10,
            'command': 'spam',
            'request_seq': 9,
            'success': False,
            'message': 'oops!',
        }
        msg = Response.from_data(**data)

        self.assertEqual(msg.type, 'response')
        self.assertEqual(msg.seq, 10)
        self.assertEqual(msg.command, 'spam')
        self.assertEqual(msg.request_seq, 9)
        self.assertFalse(msg.success)
        self.assertIsNone(msg.body)
        self.assertEqual(msg.message, 'oops!')

    def test_from_data_error_with_body(self):
        class Spam(Response):
            class ERROR_BODY(FieldsNamespace):
                FIELDS = [
                    Field('a'),
                ]

        data = {
            'type': 'response',
            'seq': 10,
            'command': 'spam',
            'request_seq': 9,
            'success': False,
            'message': 'oops!',
            'body': {'a': 'b'},
        }
        msg = Spam.from_data(**data)

        self.assertEqual(msg.type, 'response')
        self.assertEqual(msg.seq, 10)
        self.assertEqual(msg.command, 'spam')
        self.assertEqual(msg.request_seq, 9)
        self.assertFalse(msg.success)
        self.assertEqual(msg.body, {'a': 'b'})
        self.assertEqual(msg.message, 'oops!')

    def test_defaults(self):
        class Spam(Response, FakeMsg):
            SEQ = 10
            COMMAND = 'spam'

        msg = Spam('9')

        self.assertEqual(msg.type, 'response')
        self.assertEqual(msg.seq, 10)
        self.assertEqual(msg.request_seq, 9)
        self.assertEqual(msg.command, 'spam')
        self.assertTrue(msg.success)
        self.assertIsNone(msg.body)
        self.assertIsNone(msg.message)

    def test_all_args_not_error(self):
        class Spam(Response):
            class BODY(FieldsNamespace):
                FIELDS = [
                    Field('a'),
                ]

        msg = Spam('9', command='spam', success=True, body={'a': 'b'},
                   seq=10, type='response')

        self.assertEqual(msg.type, 'response')
        self.assertEqual(msg.seq, 10)
        self.assertEqual(msg.request_seq, 9)
        self.assertEqual(msg.command, 'spam')
        self.assertTrue(msg.success)
        self.assertEqual(msg.body, {'a': 'b'})
        self.assertIsNone(msg.message)

    def test_all_args_error(self):
        class Spam(Response):
            COMMAND = 'spam'
            class ERROR_BODY(FieldsNamespace):  # noqa
                FIELDS = [
                    Field('a'),
                ]

        msg = Spam('9', success=False, message='oops!', body={'a': 'b'},
                   seq=10, type='response')

        self.assertEqual(msg.type, 'response')
        self.assertEqual(msg.seq, 10)
        self.assertEqual(msg.command, 'spam')
        self.assertEqual(msg.request_seq, 9)
        self.assertFalse(msg.success)
        self.assertEqual(msg.body, Spam.ERROR_BODY(a='b'))
        self.assertEqual(msg.message, 'oops!')

    def test_no_body_not_required(self):
        class Spam(Response):
            COMMAND = 'spam'
            BODY = True
            BODY_REQUIRED = False

        msg = Spam('9')

        self.assertIsNone(msg.body)

    def test_no_error_body_not_required(self):
        class Spam(Response):
            COMMAND = 'spam'
            ERROR_BODY = True
            ERROR_BODY_REQUIRED = False

        msg = Spam('9', success=False, message='oops!')

        self.assertIsNone(msg.body)

    def test_no_args(self):
        with self.assertRaises(TypeError):
            Response()

    def test_coercion_request_seq(self):
        msg = Response('9', command='spam')

        self.assertEqual(msg.request_seq, 9)

    def test_coercion_success(self):
        msg1 = Response(9, success=1, command='spam')
        msg2 = Response(9, success=None, command='spam', message='oops!')

        self.assertIs(msg1.success, True)
        self.assertIs(msg2.success, False)

    def test_coercion_body(self):
        class Spam(Response):
            COMMAND = 'spam'
            class BODY(FieldsNamespace):  # noqa
                FIELDS = [
                    Field('a'),
                ]

        body = [('a', 'b')]
        msg = Spam(9, body=body)

        self.assertEqual(msg.body, {'a': 'b'})

        with self.assertRaises(TypeError):
            Spam(9, command='spam', body=11)

    def test_coercion_error_body(self):
        class Spam(Response):
            COMMAND = 'spam'
            class ERROR_BODY(FieldsNamespace):  # noqa
                FIELDS = [
                    Field('a'),
                ]

        body = [('a', 'b')]
        msg = Spam(9, body=body, success=False, message='oops!')

        self.assertEqual(msg.body, {'a': 'b'})

        with self.assertRaises(TypeError):
            Spam(9, command='spam', success=False, message='oops!', body=11)

    def test_validation(self):
        # request_seq

        with self.assertRaises(TypeError):
            # missing
            Response(None, command='spam')
        with self.assertRaises(TypeError):
            # missing
            Response('', command='spam')
        with self.assertRaises(TypeError):
            # couldn't convert to int
            Response(object(), command='spam')
        with self.assertRaises(ValueError):
            # not non-negative
            Response(-1, command='spam')

        # command

        with self.assertRaises(TypeError):
            # missing
            Response(9, command=None)
        with self.assertRaises(TypeError):
            # missing
            Response(9, command='')

        class Other1(Response):
            COMMAND = 'eggs'

        with self.assertRaises(ValueError):
            # does not match
            Other1(9, command='spam')

        # body

        class Other2(Response):
            class BODY(FieldsNamespace):
                FIELDS = [
                    Field('a'),
                ]

            ERROR_BODY = BODY

        with self.assertRaises(ValueError):
            # unexpected
            Response(9, command='spam', body=11)
        with self.assertRaises(TypeError):
            # missing (implicitly required)
            Other2(9, command='spam')
        with self.assertRaises(TypeError):
            # missing (explicitly required)
            Other2.BODY_REQUIRED = True
            Other2(9, command='spam')
        with self.assertRaises(ValueError):
            # unexpected (error)
            Response(9, command='spam', body=11, success=False, message=':(')
        with self.assertRaises(TypeError):
            # missing (error) (implicitly required)
            Other2(9, command='spam', success=False, message=':(')
        with self.assertRaises(TypeError):
            # missing (error) (explicitly required)
            Other2.ERROR_BODY_REQUIRED = True
            Other2(9, command='spam', success=False, message=':(')

        # message

        with self.assertRaises(TypeError):
            # missing
            Response(9, command='spam', success=False)

    def test_repr_minimal(self):
        msg = Response(9, command='spam', seq=10)
        result = repr(msg)

        self.assertEqual(result,
                         "Response(command='spam', request_seq=9, success=True, seq=10)")  # noqa

    def test_repr_full(self):
        msg = Response(9, command='spam', seq=10)
        result = repr(msg)

        self.assertEqual(result,
                         "Response(command='spam', request_seq=9, success=True, seq=10)")  # noqa

    def test_repr_error_minimal(self):
        msg = Response(9, command='spam', success=False, message='oops!',
                       seq=10)
        result = repr(msg)

        self.assertEqual(result,
                         "Response(command='spam', request_seq=9, success=False, message='oops!', seq=10)")  # noqa

    def test_repr_error_full(self):
        msg = Response(9, command='spam', success=False, message='oops!',
                       seq=10)
        result = repr(msg)

        self.assertEqual(result,
                         "Response(command='spam', request_seq=9, success=False, message='oops!', seq=10)")  # noqa

    def test_repr_subclass_minimal(self):
        class SpamResponse(Response):
            COMMAND = 'spam'

        msg = SpamResponse(9, seq=10)
        result = repr(msg)

        self.assertEqual(result,
                         "SpamResponse(request_seq=9, success=True, seq=10)")

    def test_repr_subclass_full(self):
        class SpamResponse(Response):
            COMMAND = 'spam'
            class BODY(FieldsNamespace):  # noqa
                FIELDS = [
                    Field('a'),
                ]

        msg = SpamResponse(9, body={'a': 'b'}, seq=10)
        result = repr(msg)

        self.assertEqual(result,
                         "SpamResponse(request_seq=9, success=True, body=BODY(a='b'), seq=10)")  # noqa

    def test_repr_subclass_error_minimal(self):
        class SpamResponse(Response):
            COMMAND = 'spam'

        msg = SpamResponse(9, success=False, message='oops!', seq=10)
        result = repr(msg)

        self.assertEqual(result,
                         "SpamResponse(request_seq=9, success=False, message='oops!', seq=10)")  # noqa

    def test_repr_subclass_error_full(self):
        class SpamResponse(Response):
            COMMAND = 'spam'
            class ERROR_BODY(FieldsNamespace):  # noqa
                FIELDS = [
                    Field('a'),
                ]

        msg = SpamResponse(9, success=False, message='oops!', body={'a': 'b'},
                           seq=10)
        result = repr(msg)

        self.assertEqual(result,
                         "SpamResponse(request_seq=9, success=False, message='oops!', body=ERROR_BODY(a='b'), seq=10)")  # noqa

    def test_as_data_minimal(self):
        msg = Response(9, command='spam', seq=10)
        data = msg.as_data()

        self.assertEqual(data, {
            'type': 'response',
            'seq': 10,
            'request_seq': 9,
            'command': 'spam',
            'success': True,
        })

    def test_as_data_full(self):
        class Spam(Response):
            COMMAND = 'spam'
            class BODY(FieldsNamespace):  # noqa
                FIELDS = [
                    Field('a'),
                ]

        msg = Spam(9, body={'a': 'b'}, seq=10)
        data = msg.as_data()

        self.assertEqual(data, {
            'type': 'response',
            'seq': 10,
            'request_seq': 9,
            'command': 'spam',
            'success': True,
            'body': {'a': 'b'},
        })

    def test_as_data_error_minimal(self):
        msg = Response(9, command='spam', success=False, message='oops!',
                       seq=10)
        data = msg.as_data()

        self.assertEqual(data, {
            'type': 'response',
            'seq': 10,
            'request_seq': 9,
            'command': 'spam',
            'success': False,
            'message': 'oops!',
        })

    def test_as_data_error_full(self):
        class Spam(Response):
            COMMAND = 'spam'
            class ERROR_BODY(FieldsNamespace):  # noqa
                FIELDS = [
                    Field('a'),
                ]

        msg = Spam(9, success=False, body={'a': 'b'}, message='oops!', seq=10)
        data = msg.as_data()

        self.assertEqual(data, {
            'type': 'response',
            'seq': 10,
            'request_seq': 9,
            'command': 'spam',
            'success': False,
            'message': 'oops!',
            'body': {'a': 'b'},
        })


class EventTests(unittest.TestCase):

    def test_from_data_without_body(self):
        data = {
            'type': 'event',
            'seq': 10,
            'event': 'spam',
        }
        msg = Event.from_data(**data)

        self.assertEqual(msg.type, 'event')
        self.assertEqual(msg.seq, 10)
        self.assertEqual(msg.event, 'spam')
        self.assertIsNone(msg.body)

    def test_from_data_with_body(self):
        class Spam(Event):
            class BODY(FieldsNamespace):
                FIELDS = [
                    Field('a'),
                ]

        data = {
            'type': 'event',
            'seq': 10,
            'event': 'spam',
            'body': {'a': 'b'},
        }
        msg = Spam.from_data(**data)

        self.assertEqual(msg.type, 'event')
        self.assertEqual(msg.seq, 10)
        self.assertEqual(msg.event, 'spam')
        self.assertEqual(msg.body, {'a': 'b'})

    def test_defaults(self):  # no args
        class Spam(Event, FakeMsg):
            SEQ = 10
            EVENT = 'spam'

        msg = Spam()

        self.assertEqual(msg.type, 'event')
        self.assertEqual(msg.seq, 10)
        self.assertEqual(msg.event, 'spam')
        self.assertIsNone(msg.body)

    def test_all_args(self):
        class Spam(Event):
            class BODY(FieldsNamespace):
                FIELDS = [
                    Field('a'),
                ]

        msg = Spam(event='spam', body={'a': 'b'}, seq=10, type='event')

        self.assertEqual(msg.type, 'event')
        self.assertEqual(msg.seq, 10)
        self.assertEqual(msg.event, 'spam')
        self.assertEqual(msg.body, {'a': 'b'})

    def test_no_body_not_required(self):
        class Spam(Event):
            EVENT = 'spam'
            BODY = True
            BODY_REQUIRED = False

        msg = Spam()

        self.assertIsNone(msg.body)

    def test_no_args(self):
        with self.assertRaises(TypeError):
            Event()

    def test_coercion_body(self):
        class Spam(Event):
            EVENT = 'spam'
            class BODY(FieldsNamespace):  # noqa
                FIELDS = [
                    Field('a'),
                ]

        body = [('a', 'b')]
        msg = Spam(body=body)

        self.assertEqual(msg.body, {'a': 'b'})

        with self.assertRaises(TypeError):
            Spam(event='spam', body=11)

    def test_validation(self):
        # event

        with self.assertRaises(TypeError):
            # missing
            Event(event=None)
        with self.assertRaises(TypeError):
            # missing
            Event(event='')

        class Other1(Event):
            EVENT = 'eggs'

        with self.assertRaises(ValueError):
            # does not match
            Other1(event='spam')

        # body

        class Other2(Event):
            class BODY(FieldsNamespace):
                FIELDS = [
                    Field('a'),
                ]

        with self.assertRaises(ValueError):
            # unexpected
            Event(event='spam', body=11)
        with self.assertRaises(TypeError):
            # missing (implicitly required)
            Other2(9, command='spam')
        with self.assertRaises(TypeError):
            # missing (explicitly required)
            Other2.BODY_REQUIRED = True
            Other2(9, command='spam')

    def test_repr_minimal(self):
        msg = Event(event='spam', seq=10)
        result = repr(msg)

        self.assertEqual(result, "Event(event='spam', seq=10)")

    def test_repr_full(self):
        msg = Event(event='spam', seq=10)
        result = repr(msg)

        self.assertEqual(result, "Event(event='spam', seq=10)")

    def test_repr_subclass_minimal(self):
        class SpamEvent(Event):
            EVENT = 'spam'

        msg = SpamEvent(seq=10)
        result = repr(msg)

        self.assertEqual(result, 'SpamEvent(seq=10)')

    def test_repr_subclass_full(self):
        class SpamEvent(Event):
            EVENT = 'spam'
            class BODY(FieldsNamespace):  # noqa
                FIELDS = [
                    Field('a'),
                ]

        msg = SpamEvent(body={'a': 'b'}, seq=10)
        result = repr(msg)

        self.assertEqual(result, "SpamEvent(body=BODY(a='b'), seq=10)")

    def test_as_data_minimal(self):
        msg = Event(event='spam', seq=10)
        data = msg.as_data()

        self.assertEqual(data, {
            'type': 'event',
            'seq': 10,
            'event': 'spam',
        })

    def test_as_data_full(self):
        class Spam(Event):
            EVENT = 'spam'
            class BODY(FieldsNamespace):  # noqa
                FIELDS = [
                    Field('a'),
                ]

        msg = Spam(body={'a': 'b'}, seq=10)
        data = msg.as_data()

        self.assertEqual(data, {
            'type': 'event',
            'seq': 10,
            'event': 'spam',
            'body': {'a': 'b'},
        })
