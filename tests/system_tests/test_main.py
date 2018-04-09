from textwrap import dedent
import unittest

from tests.helpers.editor import FakeEditor, get_locked_and_waiter
from tests.helpers.vsc import parse_message
from tests.helpers.workspace import PathEntry


class CLITests(unittest.TestCase):

    @property
    def workspace(self):
        try:
            return self._workspace
        except AttributeError:
            self._workspace = PathEntry()
            self.addCleanup(self._workspace.cleanup)
            self._workspace.install()
            return self._workspace

    def add_module(self, name, content):
        return self.workspace.write_module(name, dedent(content))

    def assert_received(self, received, expected):
        received = [parse_message(msg) for msg in received]
        expected = [parse_message(msg) for msg in expected]
        self.assertEqual(received, expected)

    def test_pre_init(self):
        lock, wait = get_locked_and_waiter()

        def handle_msg(msg):
            if msg.type != 'event':
                return False
            if msg.event != 'output':
                return False
            lock.release()
            return True
        filename = self.add_module('spam', '')
        with FakeEditor() as editor:
            adapter, session = editor.launch_script(
                filename,
                '--eggs',
                handlers=[
                    (handle_msg, "event 'output'"),
                ],
            )
            wait(reason="event 'output'")
        out = adapter.output

        self.assert_received(session.received, [
            {
                'type': 'event',
                'seq': 0,
                'event': 'output',
                'body': {
                    'output': 'ptvsd',
                    'data': {
                        'version': '4.0.0a5',
                    },
                    'category': 'telemetry',
                },
            },
        ])
        self.assertEqual(out, b'')
