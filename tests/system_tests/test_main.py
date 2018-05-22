import os
from textwrap import dedent
import unittest

import ptvsd
from ptvsd.socket import Address
from ptvsd.wrapper import INITIALIZE_RESPONSE # noqa
from tests.helpers.debugadapter import DebugAdapter
from tests.helpers.debugclient import EasyDebugClient as DebugClient
from tests.helpers.threading import get_locked_and_waiter
from tests.helpers.vsc import parse_message, VSCMessages
from tests.helpers.workspace import Workspace, PathEntry


#VERSION = '0+unknown'
VERSION = ptvsd.__version__


def _strip_pydevd_output(out):
    # TODO: Leave relevant lines from before the marker?
    pre, sep, out = out.partition(
        'pydev debugger: starting' + os.linesep + os.linesep)
    return out if sep else pre


def lifecycle_handshake(session, command='launch', options=None):
    with session.wait_for_event('initialized'):
        req_initialize = session.send_request(
            'initialize',
            adapterID='spam',
        )
        req_command = session.send_request(command, **options or {})
    # TODO: pre-set breakpoints
    req_done = session.send_request('configurationDone')
    return req_initialize, req_command, req_done


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

    def write_debugger_script(self, filename, port, run_as):
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


class CLITests(TestsBase, unittest.TestCase):

    def test_script_args(self):
        lockfile = self.workspace.lockfile()
        donescript, lockwait = lockfile.wait_for_script()
        filename = self.pathentry.write_module('spam', """
            import sys
            print(sys.argv)
            sys.stdout.flush()

            {}
            import time
            time.sleep(10000)
            """.format(donescript.replace('\n', '\n            ')))
        with DebugClient() as editor:
            adapter, session = editor.launch_script(
                filename,
                '--eggs',
            )
            lifecycle_handshake(session, 'launch')
            lockwait(timeout=2.0)
            session.send_request('disconnect')
        out = adapter.output

        self.assertEqual(out.decode('utf-8').strip().splitlines()[-1],
                         u"[{!r}, '--eggs']".format(filename))

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

    def test_script(self):
        argv = []
        filename = self.write_script('spam.py', """
            import sys
            print('done')
            sys.stdout.flush()
            """)
        script = self.write_debugger_script(filename, 9876, run_as='script')
        with DebugClient(port=9876) as editor:
            adapter, session = editor.host_local_debugger(argv, script)
            lifecycle_handshake(session, 'launch')
            adapter.wait()
        out = adapter.output.decode('utf-8')
        rc = adapter.exitcode

        self.assertIn('done', out.splitlines())
        self.assertEqual(rc, 0)

    # python -m ptvsd --server --port 1234 --file one.py


class LifecycleTests(TestsBase, unittest.TestCase):

    @property
    def messages(self):
        try:
            return self._messages
        except AttributeError:
            self._messages = VSCMessages()
            return self._messages

    def new_response(self, *args, **kwargs):
        return self.messages.new_response(*args, **kwargs)

    def new_event(self, *args, **kwargs):
        return self.messages.new_event(*args, **kwargs)

    def _wait_for_started(self):
        lock, wait = get_locked_and_waiter()

        # TODO: There's a race with the initial "output" event.
        def handle_msg(msg):
            if msg.type != 'event':
                return False
            if msg.event != 'output':
                return False
            lock.release()
            return True
        handlers = [
            (handle_msg, "event 'output'"),
        ]
        return handlers, (lambda: wait(reason="event 'output'"))

    def assert_received(self, received, expected):
        received = [parse_message(msg) for msg in received]
        expected = [parse_message(msg) for msg in expected]
        self.assertEqual(received, expected)

    def test_pre_init(self):
        filename = self.pathentry.write_module('spam', '')
        handlers, wait_for_started = self._wait_for_started()
        with DebugClient() as editor:
            adapter, session = editor.launch_script(
                filename,
                handlers=handlers,
                timeout=3.0,
            )
            wait_for_started()
        out = adapter.output.decode('utf-8')

        self.assert_received(session.received, [
            # TODO: Use self.new_event()...
            {
                'type': 'event',
                'seq': 0,
                'event': 'output',
                'body': {
                    'output': 'ptvsd',
                    'data': {
                        'version': VERSION,
                    },
                    'category': 'telemetry',
                },
            },
        ])
        out = _strip_pydevd_output(out)
        self.assertEqual(out, '')

    def test_launch_ptvsd_client(self):
        argv = []
        lockfile = self.workspace.lockfile()
        done, waitscript = lockfile.wait_in_script()
        filename = self.write_script('spam.py', waitscript)
        script = self.write_debugger_script(filename, 9876, run_as='script')
        with DebugClient(port=9876) as editor:
            adapter, session = editor.host_local_debugger(
                argv,
                script,
            )

            (req_initialize, req_launch, req_config
             ) = lifecycle_handshake(session, 'launch')

            done()
            adapter.wait()

        self.assert_received(session.received, [
            self.new_event(
                'output',
                category='telemetry',
                output='ptvsd',
                data={'version': VERSION}),
            self.new_response(req_initialize, **INITIALIZE_RESPONSE),
            self.new_event('initialized'),
            self.new_response(req_launch),
            self.new_response(req_config),
            self.new_event('exited', exitCode=0),
            self.new_event('terminated'),
        ])

    def test_launch_ptvsd_server(self):
        lockfile = self.workspace.lockfile()
        done, waitscript = lockfile.wait_in_script()
        filename = self.write_script('spam.py', waitscript)
        with DebugClient() as editor:
            adapter, session = editor.launch_script(
                filename,
                timeout=3.0,
            )

            (req_initialize, req_launch, req_config
             ) = lifecycle_handshake(session, 'launch')
            done()
            adapter.wait()

        self.maxDiff = None
        self.assert_received(session.received, [
            self.new_event(
                'output',
                category='telemetry',
                output='ptvsd',
                data={'version': VERSION}),
            self.new_response(req_initialize, **INITIALIZE_RESPONSE),
            self.new_event('initialized'),
            self.new_response(req_launch),
            self.new_response(req_config),
            self.new_event('exited', exitCode=0),
            self.new_event('terminated'),
        ])

    def test_attach_started_separately(self):
        lockfile = self.workspace.lockfile()
        done, waitscript = lockfile.wait_in_script()
        filename = self.write_script('spam.py', waitscript)
        addr = Address('localhost', 8888)
        with DebugAdapter.start_for_attach(addr, filename) as adapter:
            with DebugClient() as editor:
                session = editor.attach_socket(addr, adapter)

                (req_initialize, req_launch, req_config
                 ) = lifecycle_handshake(session, 'attach')
                done()
                adapter.wait()

        self.assert_received(session.received, [
            self.new_event(
                'output',
                category='telemetry',
                output='ptvsd',
                data={'version': VERSION}),
            self.new_response(req_initialize, **INITIALIZE_RESPONSE),
            self.new_event('initialized'),
            self.new_response(req_launch),
            self.new_response(req_config),
            self.new_event('process', **{
                'isLocalProcess': True,
                'systemProcessId': adapter.pid,
                'startMethod': 'attach',
                'name': filename,
            }),
            self.new_event('exited', exitCode=0),
            self.new_event('terminated'),
        ])

    def test_attach_embedded(self):
        lockfile = self.workspace.lockfile()
        done, waitscript = lockfile.wait_in_script()
        addr = Address('localhost', 8888)
        script = dedent("""
            from __future__ import print_function
            import sys
            sys.path.insert(0, {!r})
            import ptvsd
            ptvsd.enable_attach({}, redirect_output={})

            %s

            print('success!', end='')
            """).format(os.getcwd(), tuple(addr), True)
        filename = self.write_script('spam.py', script % waitscript)
        with DebugAdapter.start_embedded(addr, filename) as adapter:
            with DebugClient() as editor:
                session = editor.attach_socket(addr, adapter)

                (req_initialize, req_launch, req_config
                 ) = lifecycle_handshake(session, 'attach')
                done()
                adapter.wait()
        out = adapter.output.decode('utf-8')

        self.assert_received(session.received, [
            self.new_event(
                'output',
                category='telemetry',
                output='ptvsd',
                data={'version': VERSION}),
            self.new_response(req_initialize, **INITIALIZE_RESPONSE),
            self.new_event('initialized'),
            self.new_response(req_launch),
            self.new_response(req_config),
            self.new_event('process', **{
                'isLocalProcess': True,
                'systemProcessId': adapter.pid,
                'startMethod': 'attach',
                'name': filename,
            }),
            self.new_event('output', output='success!', category='stdout'),
            self.new_event('exited', exitCode=0),
            self.new_event('terminated'),
        ])
        self.assertIn('success!', out)

    def test_reattach(self):
        lockfile1 = self.workspace.lockfile()
        done1, waitscript1 = lockfile1.wait_in_script(timeout=5)
        lockfile2 = self.workspace.lockfile()
        done2, waitscript2 = lockfile2.wait_in_script(timeout=5)
        filename = self.write_script('spam.py', waitscript1 + waitscript2)
        addr = Address('localhost', 8888)
        with DebugAdapter.start_for_attach(addr, filename) as adapter:
            with DebugClient() as editor:
                # Attach initially.
                session1 = editor.attach_socket(addr, adapter)
                reqs = lifecycle_handshake(session1, 'attach')
                done1()
                req_disconnect = session1.send_request('disconnect')
                editor.detach(adapter)

                # Re-attach
                session2 = editor.attach_socket(addr, adapter)
                (req_initialize, req_launch, req_config
                 ) = lifecycle_handshake(session2, 'attach')
                done2()

                adapter.wait()

        #self.maxDiff = None
        self.assert_received(session1.received, [
            self.new_event(
                'output',
                category='telemetry',
                output='ptvsd',
                data={'version': VERSION}),
            self.new_response(reqs[0], **INITIALIZE_RESPONSE),
            self.new_event('initialized'),
            self.new_response(reqs[1]),
            self.new_response(reqs[2]),
            self.new_event('process', **{
                'isLocalProcess': True,
                'systemProcessId': adapter.pid,
                'startMethod': 'attach',
                'name': filename,
            }),
            self.new_response(req_disconnect),
            # TODO: Shouldn't there be a "terminated" event?
            #self.new_event('terminated'),
        ])
        self.messages.reset_all()
        self.assert_received(session2.received, [
            self.new_event(
                'output',
                category='telemetry',
                output='ptvsd',
                data={'version': VERSION}),
            self.new_response(req_initialize, **INITIALIZE_RESPONSE),
            self.new_event('initialized'),
            self.new_response(req_launch),
            self.new_response(req_config),
            self.new_event('process', **{
                'isLocalProcess': True,
                'systemProcessId': adapter.pid,
                'startMethod': 'attach',
                'name': filename,
            }),
            self.new_event('exited', exitCode=0),
            self.new_event('terminated'),
        ])

    @unittest.skip('re-attach needs fixing')
    def test_attach_unknown(self):
        lockfile = self.workspace.lockfile()
        done, waitscript = lockfile.wait_in_script()
        filename = self.write_script('spam.py', waitscript)
        with DebugClient() as editor:
            # Launch and detach.
            # TODO: This is not an ideal way to spin up a process
            # to which we can attach.  However, ptvsd has no such
            # capabilitity at present and attaching without ptvsd
            # running isn't an option currently.
            adapter, session = editor.launch_script(
                filename,
            )

            lifecycle_handshake(session, 'launch')
            editor.detach()

            # Re-attach.
            session = editor.attach()
            (req_initialize, req_launch, req_config
             ) = lifecycle_handshake(session, 'attach')

            done()
            adapter.wait()

        self.assert_received(session.received, [
            self.new_event(
                'output',
                category='telemetry',
                output='ptvsd',
                data={'version': VERSION}),
            self.new_response(req_initialize, **INITIALIZE_RESPONSE),
            self.new_event('initialized'),
            self.new_response(req_launch),
            self.new_response(req_config),
            self.new_event('exited', exitCode=0),
            self.new_event('terminated'),
        ])
