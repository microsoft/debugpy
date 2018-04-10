import unittest

from tests.helpers.debugadapter import DebugAdapter
from tests.helpers.debugclient import DebugClient
from tests.helpers.threading import get_locked_and_waiter
from tests.helpers.vsc import parse_message
from tests.helpers.workspace import Workspace, PathEntry


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
            self._workspace = Workspace()
            self.addCleanup(self._workspace.cleanup)
            return self._workspace

    @property
    def pathentry(self):
        try:
            return self._pathentry
        except AttributeError:
            self._pathentry = PathEntry()
            self.addCleanup(self._pathentry.cleanup)
            self._pathentry.install()
            return self._pathentry


class CLITests(TestsBase, unittest.TestCase):

    def test_script_args(self):
        lockfile, lockwait = self.workspace.lockfile('done.lock')
        filename = self.pathentry.write_module('spam', """
            import sys
            print(sys.argv)
            sys.stdout.flush()

            with open({!r}, 'w'):
                pass
            import time
            time.sleep(10000)
            """.format(lockfile))
        with DebugClient() as editor:
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

    def test_run_to_completion(self):
        filename = self.pathentry.write_module('spam', """
            import sys
            print('done')
            sys.stdout.flush()
            """)
        with DebugClient() as editor:
            adapter, session = editor.launch_script(
                filename,
            )
            lifecycle_handshake(session, 'launch')
            adapter.wait()
        out = adapter.output.decode('utf-8')
        rc = adapter.exitcode

        self.assertIn('done', out.splitlines())
        self.assertEqual(rc, 0)

    def test_failure(self):
        filename = self.pathentry.write_module('spam', """
            import sys
            sys.exit(42)
            """)
        with DebugClient() as editor:
            adapter, session = editor.launch_script(
                filename,
            )
            lifecycle_handshake(session, 'launch')
            adapter.wait()
        rc = adapter.exitcode

        self.assertEqual(rc, 42)


class LifecycleTests(TestsBase, unittest.TestCase):

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
        filename = self.pathentry.write_module('spam', '')
        with DebugClient() as editor:
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
