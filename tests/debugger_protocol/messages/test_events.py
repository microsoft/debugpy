import unittest

from debugger_protocol.messages import events


class StringLike:

    def __init__(self, value):
        self.value = value

    def __str__(self):
        return self.value


class EventsTests(unittest.TestCase):

    def test_implicit___all__(self):
        names = set(name
                    for name in vars(events)
                    if not name.startswith('__'))

        self.assertEqual(names, {
            'InitializedEvent',
            'StoppedEvent',
            'ContinuedEvent',
            'ExitedEvent',
            'TerminatedEvent',
            'ThreadEvent',
            'OutputEvent',
            'BreakpointEvent',
            'ModuleEvent',
            'LoadedSourceEvent',
            'ProcessEvent',
        })


class TestBase:

    NAME = None
    EVENT = None
    BODY = None
    BODY_MIN = None

    def test_event_full(self):
        event = self.EVENT(self.BODY, seq=9)

        self.assertEqual(event.event, self.NAME)
        self.assertEqual(event.body, self.BODY)

    def test_event_minimal(self):
        event = self.EVENT(self.BODY_MIN, seq=9)

        self.assertEqual(event.body, self.BODY_MIN)

    def test_event_empty_body(self):
        if self.BODY_MIN:
            with self.assertRaises(TypeError):
                self.EVENT({}, seq=9)

    def test_from_data(self):
        event = self.EVENT.from_data(
            type='event',
            seq=9,
            event=self.NAME,
            body=self.BODY,
        )

        self.assertEqual(event.body, self.BODY)

    def test_as_data(self):
        event = self.EVENT(self.BODY, seq=9)
        data = event.as_data()

        self.assertEqual(data, {
            'type': 'event',
            'seq': 9,
            'event': self.NAME,
            'body': self.BODY,
        })


class InitializedEventTests(unittest.TestCase):

    def test_event(self):
        event = events.InitializedEvent(seq=9)

        self.assertEqual(event.event, 'initialized')


class StoppedEventTests(TestBase, unittest.TestCase):

    NAME = 'stopped'
    EVENT = events.StoppedEvent
    BODY = {
        'reason': 'step',
        'description': 'descr',
        'threadId': 10,
        'text': '...',
        'allThreadsStopped': False,
    }
    BODY_MIN = {
        'reason': 'step',
    }

    def test_reasons(self):
        for reason in events.StoppedEvent.BODY.REASONS:
            with self.subTest(reason):
                body = {
                    'reason': reason,
                }
                event = events.StoppedEvent(body, seq=9)

                self.assertEqual(event.body.reason, reason)


class ContinuedEventTests(TestBase, unittest.TestCase):

    NAME = 'continued'
    EVENT = events.ContinuedEvent
    BODY = {
        'threadId': 10,
        'allThreadsContinued': True,
    }
    BODY_MIN = {
        'threadId': 10,
    }


class ExitedEventTests(TestBase, unittest.TestCase):

    NAME = 'exited'
    EVENT = events.ExitedEvent
    BODY = {
        'exitCode': 0,
    }
    BODY_MIN = BODY


class TerminatedEventTests(TestBase, unittest.TestCase):

    NAME = 'terminated'
    EVENT = events.TerminatedEvent
    BODY = {
        'restart': True,
    }
    BODY_MIN = {}


class ThreadEventTests(TestBase, unittest.TestCase):

    NAME = 'thread'
    EVENT = events.ThreadEvent
    BODY = {
        'threadId': 10,
        'reason': 'exited',
    }
    BODY_MIN = BODY

    def test_reasons(self):
        for reason in self.EVENT.BODY.REASONS:
            with self.subTest(reason):
                body = {
                    'threadId': 10,
                    'reason': reason,
                }
                event = self.EVENT(body, seq=9)

                self.assertEqual(event.body.reason, reason)


class OutputEventTests(TestBase, unittest.TestCase):

    NAME = 'output'
    EVENT = events.OutputEvent
    BODY = {
        'output': '...',
        'category': 'stdout',
        'variablesReference': 10,
        'source': '...',
        'line': 11,
        'column': 12,
        'data': None,
    }
    BODY_MIN = {
        'output': '...',
    }

    def test_categories(self):
        for category in self.EVENT.BODY.CATEGORIES:
            with self.subTest(category):
                body = dict(self.BODY, **{
                    'category': category,
                })
                event = self.EVENT(body, seq=9)

                self.assertEqual(event.body.category, category)


class BreakpointEventTests(TestBase, unittest.TestCase):

    NAME = 'breakpoint'
    EVENT = events.BreakpointEvent
    BODY = {
        'breakpoint': {
            'id': 10,
            'verified': True,
            'message': '...',
            'source': {
                'name': '...',
                'path': '...',
                'sourceReference': 15,
                'presentationHint': 'normal',
                'origin': '...',
                'sources': [
                    {'name': '...'},
                ],
                'adapterData': None,
                'checksums': [
                    {'algorithm': 'MD5', 'checksum': '...'},
                ],
            },
            'line': 11,
            'column': 12,
            'endLine': 11,
            'endColumn': 12,
        },
        'reason': 'new',
    }
    BODY_MIN = {
        'breakpoint': {
            'id': 10,
            'verified': True,
        },
        'reason': 'new',
    }

    def test_reasons(self):
        for reason in self.EVENT.BODY.REASONS:
            with self.subTest(reason):
                body = dict(self.BODY, **{
                    'reason': reason,
                })
                event = self.EVENT(body, seq=9)

                self.assertEqual(event.body.reason, reason)


class ModuleEventTests(TestBase, unittest.TestCase):

    NAME = 'module'
    EVENT = events.ModuleEvent
    BODY = {
        'module': {
            'id': 10,
            'name': '...',
            'path': '...',
            'isOptimized': False,
            'isUserCode': True,
            'version': '...',
            'symbolStatus': '...',
            'symbolFilePath': '...',
            'dateTimeStamp': '...',
            'addressRange': '...',
        },
        'reason': 'new',
    }
    BODY_MIN = {
        'module': {
            'id': 10,
            'name': '...',
        },
        'reason': 'new',
    }

    def test_reasons(self):
        for reason in self.EVENT.BODY.REASONS:
            with self.subTest(reason):
                body = dict(self.BODY, **{
                    'reason': reason,
                })
                event = self.EVENT(body, seq=9)

                self.assertEqual(event.body.reason, reason)


class LoadedSourceEventTests(TestBase, unittest.TestCase):

    NAME = 'loadedSource'
    EVENT = events.LoadedSourceEvent
    BODY = {
        'source': {
            'name': '...',
            'path': '...',
            'sourceReference': 15,
            'presentationHint': 'normal',
            'origin': '...',
            'sources': [
                {'name': '...'},
            ],
            'adapterData': None,
            'checksums': [
                {'algorithm': 'MD5', 'checksum': '...'},
            ],
        },
        'reason': 'new',
    }
    BODY_MIN = {
        'source': {},
        'reason': 'new',
    }

    def test_reasons(self):
        for reason in self.EVENT.BODY.REASONS:
            with self.subTest(reason):
                body = dict(self.BODY, **{
                    'reason': reason,
                })
                event = self.EVENT(body, seq=9)

                self.assertEqual(event.body.reason, reason)

    def test_hints(self):
        for hint in self.EVENT.BODY.FIELDS[0].datatype.HINTS:
            with self.subTest(hint):
                body = dict(self.BODY)
                body['source'].update(**{
                    'presentationHint': hint,
                })
                event = self.EVENT(body, seq=9)

                self.assertEqual(event.body.source.presentationHint, hint)


class ProcessEventTests(TestBase, unittest.TestCase):

    NAME = 'process'
    EVENT = events.ProcessEvent
    BODY = {
        'name': '...',
        'systemProcessId': 10,
        'isLocalProcess': True,
        'startMethod': 'launch',
    }
    BODY_MIN = {
        'name': '...',
    }

    def test_start_methods(self):
        for method in self.EVENT.BODY.START_METHODS:
            with self.subTest(method):
                body = dict(self.BODY, **{
                    'startMethod': method,
                })
                event = self.EVENT(body, seq=9)

                self.assertEqual(event.body.startMethod, method)
