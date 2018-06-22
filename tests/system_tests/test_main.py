import os
import os.path
from textwrap import dedent
import unittest

import ptvsd
from ptvsd.socket import Address
from ptvsd.wrapper import INITIALIZE_RESPONSE  # noqa
from tests.helpers.debugadapter import DebugAdapter
from tests.helpers.debugclient import EasyDebugClient as DebugClient
from tests.helpers.script import find_line, set_lock
from tests.helpers.threading import get_locked_and_waiter
from tests.helpers.vsc import parse_message, VSCMessages
from tests.helpers.workspace import Workspace, PathEntry


ROOT = os.path.dirname(os.path.dirname(ptvsd.__file__))


class ANYType(object):
    def __repr__(self):
        return 'ANY'
ANY = ANYType()  # noqa


def _match_value(value, expected, allowextra=True):
    if expected is ANY:
        return True

    if isinstance(expected, dict):  # TODO: Support any mapping?
        if not isinstance(value, dict):
            return False
        if not allowextra and sorted(value) != sorted(expected):
            return False
        for key, val in expected.items():
            if key not in value:
                return False
            if not _match_value(value[key], val):
                return False
        return True
    elif isinstance(expected, str):  # str is a special case of sequence.
        if not isinstance(value, str):
            return False
        return value == expected
    elif isinstance(expected, (list, tuple)):  # TODO: Support any sequence?
        if not isinstance(value, (list, tuple)):
            return False
        if not allowextra and len(value) < len(expected):
            return False
        for val, exp in zip(value, expected):
            if not _match_value(val, exp):
                return False
        return True
    else:
        return value == expected


def _match_event(msg, event, **body):
    if msg.type != 'event':
        return False
    if msg.event != event:
        return False
    return _match_value(msg.body, body)


def _get_version(received, actual=ptvsd.__version__):
    version = actual
    for msg in received:
        if _match_event(msg, 'output', data={'version': ANY}):
            if msg.body['data']['version'] != actual:
                version = '0+unknown'
            break
    return version


def _find_events(received, event, **body):
    for i, msg in enumerate(received):
        if _match_event(msg, event, **body):
            yield i, msg


def _strip_messages(received, match_msg):
    msgs = iter(received)
    for msg in msgs:
        if match_msg(msg):
            break
        yield msg
    stripped = 1
    for msg in msgs:
        if match_msg(msg):
            stripped += 1
        else:
            yield msg._replace(seq=msg.seq - stripped)


def _strip_exit(received):
    def match(msg):
        if _match_event(msg, 'exited'):
            return True
        if _match_event(msg, 'terminated'):
            return True
        if _match_event(msg, 'thread', reason=u'exited'):
            return True
        return False
    return _strip_messages(received, match)


def _strip_output_event(received, output):
    matched = False

    def match(msg):
        if matched:
            return False
        else:
            return _match_event(msg, 'output', output=output)
    return _strip_messages(received, match)


def _strip_newline_output_events(received):
    def match(msg):
        return _match_event(msg, 'output', output=u'\n')
    return _strip_messages(received, match)


def _strip_pydevd_output(out):
    # TODO: Leave relevant lines from before the marker?
    pre, sep, out = out.partition(
        'pydev debugger: starting' + os.linesep + os.linesep)
    return out if sep else pre


def lifecycle_handshake(session, command='launch', options=None,
                        breakpoints=None, excbreakpoints=None,
                        threads=False):
    with session.wait_for_event('initialized'):
        req_initialize = session.send_request(
            'initialize',
            adapterID='spam',
        )
    req_command = session.send_request(command, **options or {})
    req_threads = session.send_request('threads') if threads else None

    reqs_bps = []
    reqs_exc = []
    for req in breakpoints or ():
        reqs_bps.append(
            session.send_request('setBreakpoints', **req))
    for req in excbreakpoints or ():
        reqs_bps.append(
            session.send_request('setExceptionBreakpoints', **req))

    req_done = session.send_request('configurationDone')
    return (req_initialize, req_command, req_done,
            reqs_bps, reqs_exc, req_threads)


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
        out = adapter.output.decode('utf-8')

        self.assertIn(u"[{!r}, '--eggs']".format(filename),
                      out.strip().splitlines())

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
        from tests.helpers.message import assert_messages_equal
        received = [parse_message(msg) for msg in received]
        expected = [parse_message(msg) for msg in expected]
        assert_messages_equal(received, expected)

    def new_version_event(self, received):
        version = _get_version(received)
        return self.new_event(
            'output',
            category='telemetry',
            output='ptvsd',
            data={'version': version},
        )

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

        received = list(_strip_newline_output_events(session.received))
        self.assert_received(received, [
            self.new_version_event(session.received),
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
            with session.wait_for_event('exited'):
                with session.wait_for_event('thread'):
                    (req_initialize, req_launch, req_config, _, _, _
                     ) = lifecycle_handshake(session, 'launch')

                done()
                adapter.wait()

        # Skipping the 'thread exited' and 'terminated' messages which
        # may appear randomly in the received list.
        received = list(_strip_newline_output_events(session.received))
        self.assert_received(received[:7], [
            self.new_version_event(session.received),
            self.new_response(req_initialize, **INITIALIZE_RESPONSE),
            self.new_event('initialized'),
            self.new_response(req_launch),
            self.new_response(req_config),
            self.new_event('process', **{
                'isLocalProcess': True,
                'systemProcessId': adapter.pid,
                'startMethod': 'launch',
                'name': filename,
            }),
            self.new_event('thread', reason='started', threadId=1),
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

            with session.wait_for_event('thread'):
                (req_initialize, req_launch, req_config, _, _, _
                 ) = lifecycle_handshake(session, 'launch')

            done()
            adapter.wait()

        received = list(_strip_newline_output_events(session.received))
        self.assert_received(received[:7], [
            self.new_version_event(session.received),
            self.new_response(req_initialize, **INITIALIZE_RESPONSE),
            self.new_event('initialized'),
            self.new_response(req_launch),
            self.new_response(req_config),
            self.new_event('process', **{
                'isLocalProcess': True,
                'systemProcessId': adapter.pid,
                'startMethod': 'launch',
                'name': filename,
            }),
            self.new_event('thread', reason='started', threadId=1),
            #self.new_event('thread', reason='exited', threadId=1),
            #self.new_event('exited', exitCode=0),
            #self.new_event('terminated'),
        ])

    def test_attach_started_separately(self):
        lockfile = self.workspace.lockfile()
        done, waitscript = lockfile.wait_in_script()
        filename = self.write_script('spam.py', waitscript)
        addr = Address('localhost', 8888)
        with DebugAdapter.start_for_attach(addr, filename) as adapter:
            with DebugClient() as editor:
                session = editor.attach_socket(addr, adapter)

                with session.wait_for_event('thread'):
                    (req_initialize, req_launch, req_config, _, _, _
                     ) = lifecycle_handshake(session, 'attach')

                done()
                adapter.wait()

        received = list(_strip_newline_output_events(session.received))
        self.assert_received(received[:7], [
            self.new_version_event(session.received),
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
            self.new_event('thread', reason='started', threadId=1),
            #self.new_event('thread', reason='exited', threadId=1),
            #self.new_event('exited', exitCode=0),
            #self.new_event('terminated'),
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

                (req_initialize, req_launch, req_config, _, _, _
                 ) = lifecycle_handshake(session, 'attach')
                done()
                adapter.wait()
        out = adapter.output.decode('utf-8')

        received = list(_strip_newline_output_events(session.received))
        self.assert_received(received, [
            self.new_version_event(session.received),
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
                with session1.wait_for_event('thread'):
                    reqs = lifecycle_handshake(session1, 'attach')
                    done1()
                req_disconnect = session1.send_request('disconnect')
                editor.detach(adapter)

                # Re-attach
                session2 = editor.attach_socket(addr, adapter)
                (req_initialize, req_launch, req_config, _, _, _
                 ) = lifecycle_handshake(session2, 'attach')
                done2()

                adapter.wait()

        received = list(_strip_newline_output_events(session1.received))
        self.assert_received(received, [
            self.new_version_event(session1.received),
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
            self.new_event('thread', reason='started', threadId=1),
            self.new_response(req_disconnect),
        ])
        self.messages.reset_all()
        received = list(_strip_newline_output_events(session2.received))
        self.assert_received(received, [
            self.new_version_event(session2.received),
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

    @unittest.skip('not implemented')
    def test_attach_exit_during_session(self):
        # TODO: Ensure we see the "terminated" and "exited" events.
        raise NotImplementedError

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
            (req_initialize, req_launch, req_config, _, _, _
             ) = lifecycle_handshake(session, 'attach')

            done()
            adapter.wait()

        received = list(_strip_newline_output_events(session.received))
        self.assert_received(received, [
            self.new_version_event(session.received),
            self.new_response(req_initialize, **INITIALIZE_RESPONSE),
            self.new_event('initialized'),
            self.new_response(req_launch),
            self.new_response(req_config),
            self.new_event('exited', exitCode=0),
            self.new_event('terminated'),
        ])

    def test_attach_breakpoints(self):
        # See https://github.com/Microsoft/ptvsd/issues/448.
        addr = Address('localhost', 8888)
        filename = self.write_script('spam.py', """
            import time
            import sys
            sys.path.insert(0, {!r})
            import ptvsd

            addr = {}
            ptvsd.enable_attach(addr)
            print('waiting for attach')
            time.sleep(0.1)
            # <waiting>
            ptvsd.wait_for_attach()
            # <attached>
            print('attached!')
            # <bp 2>
            print('done waiting')
            """.format(ROOT, tuple(addr)))
        lockfile1 = self.workspace.lockfile()
        done1, _ = set_lock(filename, lockfile1, 'waiting')
        lockfile2 = self.workspace.lockfile()
        done2, script = set_lock(filename, lockfile2, 'bp 2')

        bp1 = find_line(script, 'attached')
        bp2 = find_line(script, 'bp 2')
        breakpoints = [{
            'source': {'path': filename},
            'breakpoints': [
                {'line': bp1},
                {'line': bp2},
            ],
        }]

        adapter = DebugAdapter.start_embedded(addr, filename)
        with adapter:
            out1 = next(adapter.output)
            line = adapter.output.readline()
            while line:
                out1 += line
                line = adapter.output.readline()
            done1()

            with DebugClient() as editor:
                session = editor.attach_socket(addr, adapter)

                # TODO: There appears to be a small race that may
                # cause the test to fail here.
                with session.wait_for_event('stopped'):
                    with session.wait_for_event('thread') as result:
                        with session.wait_for_event('process'):
                            (req_init, req_attach, req_config,
                             reqs_bps, _, req_threads1,
                             ) = lifecycle_handshake(session, 'attach',
                                                     breakpoints=breakpoints,
                                                     threads=True)
                        req_bps, = reqs_bps  # There should only be one.
                    tid = result['msg'].body['threadId']
                req_threads2 = session.send_request('threads')
                req_stacktrace1 = session.send_request(
                    'stackTrace',
                    threadId=tid,
                )
                out2 = str(adapter.output)

                done2()
                with session.wait_for_event('stopped'):
                    with session.wait_for_event('continued'):
                        req_continue1 = session.send_request(
                            'continue',
                            threadId=tid,
                        )
                req_threads3 = session.send_request('threads')
                req_stacktrace2 = session.send_request(
                    'stackTrace',
                    threadId=tid,
                )
                out3 = str(adapter.output)

                with session.wait_for_event('continued'):
                    req_continue2 = session.send_request(
                        'continue',
                        threadId=tid,
                    )

                adapter.wait()
            out4 = str(adapter.output)

        # Output between enable_attach() and wait_for_attach() may
        # be sent at a relatively arbitrary time (or not at all).
        # So we ignore it by removing it from the message list.
        received = list(_strip_output_event(session.received,
                                            u'waiting for attach'))
        received = list(_strip_newline_output_events(received))
        # There's an ordering race with continue/continued that pops
        # up occasionally.  We work around that by manually fixing the
        # order.
        for pos, msg in _find_events(received, 'continued'):
            prev = received[pos-1]
            if prev.type != 'response' or prev.command != 'continue':
                received.pop(pos-1)
                received.insert(pos + 1, prev)
        # Sometimes the proc ends before the exited and terminated
        # events are received.
        received = list(_strip_exit(received))
        self.assert_received(received, [
            self.new_version_event(session.received),
            self.new_response(req_init, **INITIALIZE_RESPONSE),
            self.new_event('initialized'),
            self.new_response(req_attach),
            self.new_event(
                'thread',
                threadId=tid,
                reason='started',
            ),
            self.new_response(req_threads1, **{
                'threads': [{
                    'id': 1,
                    'name': 'MainThread',
                }],
            }),
            self.new_response(req_bps, **{
                'breakpoints': [{
                    'id': 1,
                    'line': bp1,
                    'verified': True,
                }, {
                    'id': 2,
                    'line': bp2,
                    'verified': True,
                }],
            }),
            self.new_response(req_config),
            self.new_event('process', **{
                'isLocalProcess': True,
                'systemProcessId': adapter.pid,
                'startMethod': 'attach',
                'name': filename,
            }),
            self.new_event(
                'thread',
                threadId=tid,
                reason='started',
            ),
            self.new_event(
                'stopped',
                threadId=tid,
                reason='breakpoint',
                description=None,
                text=None,
            ),
            self.new_response(req_threads2, **{
                'threads': [{
                    'id': 1,
                    'name': 'MainThread',
                }],
            }),
            self.new_event(
                'module',
                module={
                    'id': 1,
                    'name': '__main__',
                    'path': filename,
                    'package': None,
                },
                reason='new',
            ),
            self.new_response(req_stacktrace1, **{
                'totalFrames': 1,
                'stackFrames': [{
                    'id': 1,
                    'name': '<module>',
                    'source': {
                        'path': filename,
                        'sourceReference': 1,
                    },
                    'line': bp1,
                    'column': 1,
                }],
            }),
            self.new_response(req_continue1),
            self.new_event('continued', threadId=tid),
            self.new_event(
                'output',
                category='stdout',
                output='attached!',
            ),
            self.new_event(
                'stopped',
                threadId=tid,
                reason='breakpoint',
                description=None,
                text=None,
            ),
            self.new_response(req_threads3, **{
                'threads': [{
                    'id': 1,
                    'name': 'MainThread',
                }],
            }),
            self.new_response(req_stacktrace2, **{
                'totalFrames': 1,
                'stackFrames': [{
                    'id': 2,  # TODO: Isn't this the same frame as before?
                    'name': '<module>',
                    'source': {
                        'path': filename,
                        'sourceReference': 1,
                    },
                    'line': bp2,
                    'column': 1,
                }],
            }),
            self.new_response(req_continue2),
            self.new_event('continued', threadId=tid),
            self.new_event(
                'output',
                category='stdout',
                output='done waiting',
            ),
            #self.new_event(
            #    'thread',
            #    threadId=tid,
            #    reason='exited',
            #),
            #self.new_event('exited', exitCode=0),
            #self.new_event('terminated'),
        ])
        # before attaching
        self.assertIn(b'waiting for attach', out1)
        self.assertNotIn(b'attached!', out1)
        # after attaching
        self.assertNotIn('attached!', out2)
        # after bp1 continue
        self.assertIn('attached!', out3)
        self.assertNotIn('done waiting', out3)
        # after bp2 continue
        self.assertIn('done waiting', out4)

    def test_nodebug(self):
        lockfile = self.workspace.lockfile()
        done, waitscript = lockfile.wait_in_script()
        filename = self.write_script('spam.py', dedent("""
            print('+ before')

            {}

            print('+ after')
            """).format(waitscript))
        with DebugClient(port=9876) as editor:
            adapter, session = editor.host_local_debugger(
                argv=[
                    '--nodebug',
                    filename,
                ],
            )

            (req_initialize, req_launch, req_config, _, _, _
             ) = lifecycle_handshake(session, 'launch')

            done()
            adapter.wait()

        received = list(_strip_newline_output_events(session.received))
        self.assert_received(received[:9], [
            self.new_version_event(session.received),
            self.new_response(req_initialize, **INITIALIZE_RESPONSE),
            self.new_event('initialized'),
            self.new_response(req_launch),
            self.new_event('output',
                           output='+ before',
                           category='stdout'),
            self.new_response(req_config),
            self.new_event('output',
                           output='+ after',
                           category='stdout'),
            self.new_event('exited', exitCode=0),
            self.new_event('terminated'),
        ])
