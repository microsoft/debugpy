from textwrap import dedent
import unittest

from tests.helpers.editor import FakeEditor, get_locked_and_waiter
from tests.helpers.vsc import parse_message
from tests.helpers.workspace import PathEntry


def lifecycle_handshake(session, command='launch', options=None):
    with session.wait_for_event('initialized'):
        session.send_request(
            'initialize',
            adapterID='spam',
        )
        session.send_request(command, **options or {})
    # TODO: pre-set breakpoints
    session.send_request('configurationDone')


class TestsBase(object):

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


class CLITests(TestsBase, unittest.TestCase):

    def test_script_args(self):
        lockfile, lockwait = self.workspace.lockfile('done.lock')
        filename = self.add_module('spam', """
            import sys
            print(sys.argv)
            sys.stdout.flush()

            with open({!r}, 'w'):
                pass
            import time
            time.sleep(10000)
            """.format(lockfile))
        with FakeEditor() as editor:
            adapter, session = editor.launch_script(
                filename,
                '--eggs',
            )
            lifecycle_handshake(session, 'launch')
            lockwait(timeout=2.0)
            session.send_request('disconnect')
        out = adapter.output

        self.assertEqual(out.decode('utf-8'),
                         "[{!r}, '--eggs']\n".format(filename))


class LifecycleTests(TestsBase, unittest.TestCase):

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

    def test_run_to_completion(self):
        filename = self.add_module('spam', """
            import sys
            print('done')
            sys.stdout.flush()
            """)
        with FakeEditor() as editor:
            adapter, session = editor.launch_script(
                filename,
                '--eggs',
            )
            lifecycle_handshake(session, 'launch')
            adapter.wait()
        out = adapter.output.decode('utf-8')
        rc = adapter.returncode

        self.assertIn('done', out.splitlines())
        self.assertEqual(rc, 0)
