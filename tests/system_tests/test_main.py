import os
import unittest

from tests.helpers.debugclient import EasyDebugClient as DebugClient
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

    def write_script(self, name, content):
        return self.workspace.write_python_script(name, content=content)


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


class DebugTests(TestsBase, unittest.TestCase):

    def write_debugger(self, filename, port, run_as):
        cwd = os.getcwd()
        kwargs = {
            'filename': filename,
            'port_num': port,
            'debug_id': None,
            'debug_options': None,
            'run_as': run_as,
        }
        return self.write_script('debugger.py', """
            import sys
            sys.path.insert(0, {!r})
            from ptvsd.debugger import debug
            debug(
                {filename!r},
                {port_num!r},
                {debug_id!r},
                {debug_options!r},
                {run_as!r},
            )
            """.format(cwd, **kwargs))

    def test_script(self):
        argv = []
        filename = self.write_script('spam.py', """
            import sys
            print('done')
            sys.stdout.flush()
            """)
        debugger = self.write_debugger(filename, port=9876, run_as='script')
        with DebugClient(port=9876) as editor:
            adapter, session = editor.host_local_debugger(argv, debugger)
            lifecycle_handshake(session, 'launch')
            adapter.wait()
        out = adapter.output.decode('utf-8')
        rc = adapter.exitcode

        self.assertIn('done', out.splitlines())
        self.assertEqual(rc, 0)


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
