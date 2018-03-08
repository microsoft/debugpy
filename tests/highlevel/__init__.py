from collections import namedtuple
import contextlib
import itertools
import platform
try:
    import urllib.parse as urllib
except ImportError:
    import urllib

from _pydevd_bundle import pydevd_xml
from _pydevd_bundle.pydevd_comm import (
    CMD_VERSION,
    CMD_LIST_THREADS,
    CMD_THREAD_SUSPEND,
    CMD_REDIRECT_OUTPUT,
    CMD_RETURN,
    CMD_RUN,
    CMD_STEP_CAUGHT_EXCEPTION,
    CMD_SEND_CURR_EXCEPTION_TRACE,
    CMD_THREAD_CREATE,
    CMD_GET_VARIABLE,
)

from tests.helpers.protocol import MessageCounters
from tests.helpers.pydevd import FakePyDevd
from tests.helpers.vsc import FakeVSC


OS_ID = 'WINDOWS' if platform.system() == 'Windows' else 'UNIX'


class Thread(namedtuple('Thread', 'id name')):
    """Information about a thread."""

    PREFIX = 'Thread-'

    @classmethod
    def from_raw(cls, raw):
        """Return a Thread corresponding to the given value."""
        if isinstance(raw, cls):
            return raw
        elif isinstance(raw, str):
            return cls(None, raw)
        elif isinstance(raw, int):
            return cls(raw)
        else:
            return cls(*raw)

    def __new__(cls, id, name=None):
        id = int(id) if id or id == 0 else None
        name = str(name) if name else cls.PREFIX + str(id)
        self = super(Thread, cls).__new__(cls, id, name)
        return self

    def __init__(self, *args, **kwargs):
        if self.id is None:
            raise TypeError('missing id')


class PyDevdMessages(object):

    protocol = FakePyDevd.PROTOCOL

    def __init__(self,
                 request_seq=1000000000,  # ptvsd requests to pydevd
                 response_seq=0,  # PyDevd responses/events to ptvsd
                 event_seq=None,
                 ):
        self.counters = MessageCounters(
            request_seq,
            response_seq,
            event_seq,
        )

    def __getattr__(self, name):
        return getattr(self.counters, name)

    def new_request(self, cmdid, *args, **kwargs):
        """Return a new PyDevd request message."""
        seq = kwargs.pop('seq', None)
        if seq is None:
            seq = self.counters.next_request()
        return self._new_message(cmdid, seq, args, **kwargs)

    def new_response(self, req, *args):
        """Return a new VSC response message."""
        #seq = kwargs.pop('seq', None)
        #if seq is None:
        #    seq = next(self.response_seq)
        req = self.protocol.parse(req)
        return self._new_message(req.cmdid, req.seq, args)

    def new_event(self, cmdid, *args, **kwargs):
        """Return a new VSC event message."""
        seq = kwargs.pop('seq', None)
        if seq is None:
            seq = self.counters.next_event()
        return self._new_message(cmdid, seq, args, **kwargs)

    def _new_message(self, cmdid, seq, args=()):
        text = '\t'.join(args)
        msg = (cmdid, seq, text)
        return self.protocol.parse(msg)

    def format_threads(self, *threads):
        text = '<xml>'
        for thread in threads:  # (tid, tname)
            text += '<thread id="{}" name="{}" />'.format(*thread)
        text += '</xml>'
        return text

    def format_frames(self, threadid, reason, *frames):
        text = '<xml>'
        text += '<thread id="{}" stop_reason="{}">'.format(threadid, reason)
        fmt = '<frame id="{}" name="{}" file="{}" line="{}" />'
        for frame in frames:  # (fid, func, filename, line)
            text += fmt.format(*frame)
        text += '</thread>'
        text += '</xml>'
        return text

    def format_variables(self, *variables):
        text = '<xml>'
        for name, value in variables:
            if isinstance(value, str) and value.startswith('err:'):
                value = pydevd_xml.ExceptionOnEvaluate(value[4:])
            text += pydevd_xml.var_to_xml(value, name)
        text += '</xml>'
        return urllib.quote(text)

    def format_exception(self, threadid, exc, frame):
        frameid, _, _, _ = frame
        name = pydevd_xml.make_valid_xml_value(type(exc).__name__)
        description = pydevd_xml.make_valid_xml_value(str(exc))

        info = '<xml>'
        info += '<thread id="{}" />'.format(threadid)
        info += '</xml>'
        return '{}\t{}\t{}\t{}'.format(
            frameid,
            name or 'exception: type unknown',
            description or 'exception: no description',
            self.format_frames(
                threadid,
                CMD_SEND_CURR_EXCEPTION_TRACE,
                frame,
            ),
        )


class VSCMessages(object):

    protocol = FakeVSC.PROTOCOL

    def __init__(self,
                 request_seq=0,  # VSC requests to ptvsd
                 response_seq=0,  # ptvsd responses/events to VSC
                 event_seq=None,
                 ):
        self.counters = MessageCounters(
            request_seq,
            response_seq,
            event_seq,
        )

    def __getattr__(self, name):
        return getattr(self.counters, name)

    def new_request(self, command, seq=None, **args):
        """Return a new VSC request message."""
        if seq is None:
            seq = self.counters.next_request()
        return {
            'type': 'request',
            'seq': seq,
            'command': command,
            'arguments': args,
        }

    def new_response(self, req, seq=None, **body):
        """Return a new VSC response message."""
        return self._new_response(req, None, seq, body)

    def new_failure(self, req, err, seq=None, **body):
        """Return a new VSC response message."""
        return self._new_response(req, err, body=body)

    def _new_response(self, req, err=None, seq=None, body=None):
        if seq is None:
            seq = self.counters.next_response()
        return {
            'type': 'response',
            'seq': seq,
            'request_seq': req['seq'],
            'command': req['command'],
            'success': err is None,
            'message': err or '',
            'body': body,
        }

    def new_event(self, eventname, seq=None, **body):
        """Return a new VSC event message."""
        if seq is None:
            seq = self.counters.next_event()
        return {
            'type': 'event',
            'seq': seq,
            'event': eventname,
            'body': body,
        }


class PyDevdLifecycle(object):

    def __init__(self, fix):
        self._fix = fix

    @contextlib.contextmanager
    def _wait_for_initialized(self):
        with self._fix.expect_command(CMD_REDIRECT_OUTPUT):
            with self._fix.expect_command(CMD_RUN):
                yield

    def _initialize(self):
        version = self._fix.fake.VERSION
        self._fix.set_response(CMD_VERSION, version)

    def notify_main_thread(self):
        self._fix.notify_main_thread()


class VSCLifecycle(object):

    PORT = 8888

    MIN_INITIALIZE_ARGS = {
        'adapterID': '<an adapter ID>',
    }

    def __init__(self, fix, pydevd=None, hidden=None):
        self._fix = fix
        self._pydevd = pydevd
        self._hidden = hidden or fix.hidden

    def launched(self, port=None, **kwargs):
        def start():
            self.launch(**kwargs)
        return self._started(start, port)

    def attached(self, port=None, **kwargs):
        def start():
            self.attach(**kwargs)
        return self._started(start, port)

    def launch(self, **kwargs):
        """Initialize the debugger protocol and then launch."""
        with self._hidden():
            self._handshake('launch', **kwargs)

    def attach(self, **kwargs):
        """Initialize the debugger protocol and then attach."""
        with self._hidden():
            self._handshake('attach', **kwargs)

    def disconnect(self, **reqargs):
        self._send_request('disconnect', reqargs)
        # TODO: wait for an exit event?
        # TODO: call self._fix.vsc.close()?

    # internal methods

    @contextlib.contextmanager
    def _started(self, start, port):
        if port is None:
            port = self.PORT
        addr = (None, port)
        with self._fix.fake.start(addr):
            with self._fix.disconnect_when_done():
                start()
                yield

    def _handshake(self, command, threads=None, config=None,
                   default_threads=True, process=True, reset=True,
                   **kwargs):
        initargs = dict(
            kwargs.pop('initargs', None) or {},
            disconnect=kwargs.pop('disconnect', True),
        )
        with self._fix.wait_for_event('initialized'):
            self._initialize(**initargs)
            self._fix.send_request(command, **kwargs)

        if threads:
            self._fix.set_threads(*threads,
                                  **dict(default_threads=default_threads))

        self._handle_config(**config or {})
        with self._wait_for_debugger_init():
            self._fix.send_request('configurationDone')

        if process:
            with self._fix.wait_for_event('process'):
                with self._fix.wait_for_event('thread'):
                    if self._pydevd:
                        self._pydevd.notify_main_thread()

        if reset:
            self._fix.reset()
        else:
            self._fix.assert_no_failures()

    @contextlib.contextmanager
    def _wait_for_debugger_init(self):
        if self._pydevd:
            with self._pydevd._wait_for_initialized():
                yield
        else:
                yield

    def _initialize(self, **reqargs):
        """
        See https://code.visualstudio.com/docs/extensionAPI/api-debugging#_the-vs-code-debug-protocol-in-a-nutshell
        """  # noqa
        def handle_response(resp, _):
            self._capabilities = resp.body
        if self._pydevd:
            self._pydevd._initialize()
        self._fix.send_request(
            'initialize',
            dict(self.MIN_INITIALIZE_ARGS, **reqargs),
            handle_response,
        )

    def _handle_config(self, breakpoints=None, excbreakpoints=None):
        if breakpoints:
            self._fix.send_request(
                'setBreakpoints',
                self._parse_breakpoints(breakpoints),
            )
        if excbreakpoints:
            self._fix.send_request(
                'setExceptionBreakpoints',
                self._parse_breakpoints(excbreakpoints),
            )

    def _parse_breakpoints(self, breakpoints):
        for bp in breakpoints or ():
            raise NotImplementedError


class FixtureBase(object):
    """Base class for protocol daemon test fixtures."""

    def __init__(self, new_fake, new_msgs):
        if not callable(new_fake):
            raise ValueError('bad new_fake {!r}'.format(new_fake))

        self._new_fake = new_fake
        self.msgs = new_msgs()
        self._hidden = False

    @property
    def fake(self):
        try:
            return self._fake
        except AttributeError:
            self._fake = self.new_fake()
            return self._fake

    @property
    def ishidden(self):
        return self._hidden

    @contextlib.contextmanager
    def hidden(self):
        received = self.fake.received
        orig = self._hidden
        self._hidden = True
        try:
            yield
        finally:
            self._hidden = orig
            self.fake.reset(*received)

    def set_fake(self, fake):
        if hasattr(self, '_fake'):
            raise AttributeError('fake already set')
        self._fake = fake

    def new_fake(self, handler=None, **kwargs):
        """Return a new fake that may be used in tests."""
        return self._new_fake(handler=handler, **kwargs)

    def assert_no_failures(self):
        assert self.fake.failures == [], self.fake.failures

    def reset(self):
        self.assert_no_failures()
        self.fake.reset()


class PyDevdFixture(FixtureBase):
    """A test fixture for the PyDevd protocol."""

    FAKE = FakePyDevd
    MSGS = PyDevdMessages

    def __init__(self, new_fake=None):
        if new_fake is None:
            new_fake = self.FAKE
        super(PyDevdFixture, self).__init__(new_fake, self.MSGS)
        self._default_threads = None

    def notify_main_thread(self):
        main = (1, 'MainThead')
        self.send_event(
            CMD_THREAD_CREATE,
            self.msgs.format_threads(main),
        )

    @contextlib.contextmanager
    def expect_command(self, cmdid):
        yield
        if self._hidden:
            self.msgs.next_request()

    def set_response(self, cmdid, payload, **kwargs):
        self.fake.add_pending_response(cmdid, payload, **kwargs)
        if self._hidden:
            self.msgs.next_request()

    def send_event(self, cmdid, payload):
        event = self.msgs.new_event(cmdid, payload)
        self.fake.send_event(event)

    def set_threads_response(self, threads, default_threads=True):
        threads = [Thread.from_raw(t) for t in threads]
        if default_threads:
            threads = self._add_default_threads(threads)

        text = self.msgs.format_threads(*threads)
        self.set_response(CMD_RETURN, text, reqid=CMD_LIST_THREADS)
        return threads

    def _add_default_threads(self, threads):
        if self._default_threads is not None:
            return threads
        defaults = {
            'MainThread',
            'ptvsd.Server',
            'pydevd.thread1',
            'pydevd.thread2',
        }
        seen = set()
        for thread in threads:
            tid, tname = thread
            seen.add(tid)
            if tname in defaults:
                defaults.remove(tname)
        ids = (id for id in itertools.count(1) if id not in seen)
        allthreads = []
        for tname in defaults:
            tid = next(ids)
            thread = Thread(tid, tname)
            allthreads.append(thread)
        self._default_threads = list(allthreads)
        allthreads.extend(threads)
        return allthreads

    def send_suspend_event(self, thread, reason, *stack):
        thread = Thread.from_raw(thread)
        self._suspend(thread, reason, stack)

    def send_pause_event(self, thread, *stack):
        thread = Thread.from_raw(thread)
        reason = CMD_THREAD_SUSPEND
        self._suspend(thread, reason, stack)

    def _suspend(self, thread, reason, stack):
        self.send_event(
            CMD_THREAD_SUSPEND,
            self.msgs.format_frames(thread.id, reason, *stack),
        )

    def send_caught_exception_events(self, thread, exc, *stack):
        thread = Thread.from_raw(thread)
        reason = CMD_STEP_CAUGHT_EXCEPTION
        self._exception(thread, exc, reason, stack)

    def _exception(self, thread, exc, reason, stack):
        self.send_event(
            CMD_SEND_CURR_EXCEPTION_TRACE,
            self.msgs.format_exception(thread.id, exc, *stack),
        )
        self.send_suspend_event(thread, reason, *stack)
        #self.set_exception_var_response(exc)

    def set_exception_var_response(self, exc):
        self.set_response(
            CMD_GET_VARIABLE,
            self.msgs.format_variables(
                ('???', '???'),
                ('???', exc),
            ),
        )


class VSCFixture(FixtureBase):
    """A test fixture for the DAP."""

    FAKE = FakeVSC
    MSGS = VSCMessages
    LIFECYCLE = VSCLifecycle
    START_ADAPTER = None

    def __init__(self, new_fake=None, start_adapter=None):
        if new_fake is None:
            new_fake = self.FAKE
        if start_adapter is None:
            start_adapter = self.START_ADAPTER
        elif not callable(start_adapter):
            raise ValueError('bad start_adapter {!r}'.format(start_adapter))

        def new_fake(start_adapter=start_adapter, handler=None,
                     _new_fake=new_fake):
            return _new_fake(start_adapter, handler=handler)
        super(VSCFixture, self).__init__(new_fake, self.MSGS)

    @property
    def vsc(self):
        return self.fake

    @property
    def vsc_msgs(self):
        return self.msgs

    @property
    def lifecycle(self):
        try:
            return self._lifecycle
        except AttributeError:
            self._lifecycle = self.LIFECYCLE(self)
            return self._lifecycle

    def send_request(self, command, args=None, handle_response=None):
        kwargs = dict(args or {}, handler=handle_response)
        with self._wait_for_response(command, **kwargs) as req:
            self.fake.send_request(req)
        return req

    @contextlib.contextmanager
    def _wait_for_response(self, command, *args, **kwargs):
        handler = kwargs.pop('handler', None)
        req = self.msgs.new_request(command, *args, **kwargs)
        with self.fake.wait_for_response(req, handler=handler):
            yield req
        if self._hidden:
            self.msgs.next_response()

    @contextlib.contextmanager
    def wait_for_event(self, event, *args, **kwargs):
        with self.fake.wait_for_event(event, *args, **kwargs):
            yield
        if self._hidden:
            self.msgs.next_event()

    @contextlib.contextmanager
    def _wait_for_events(self, events):
        if not events:
            yield
            return
        with self._wait_for_events(events[1:]):
            with self.wait_for_event(events[0]):
                yield

    @contextlib.contextmanager
    def disconnect_when_done(self):
        try:
            yield
        finally:
            self.send_request('disconnect')


class HighlevelFixture(object):

    DAEMON = FakeVSC
    DEBUGGER = FakePyDevd

    def __init__(self, vsc=None, pydevd=None):
        if vsc is None:
            self._new_vsc = self.DAEMON
            vsc = VSCFixture(new_fake=self._new_fake_vsc)
        elif callable(vsc):
            self._new_vsc = vsc
            vsc = VSCFixture(new_fake=self._new_fake_vsc)
        else:
            self._new_vsc = None
        self._vsc = vsc

        if pydevd is None:
            pydevd = PyDevdFixture(self.DEBUGGER)
        elif callable(pydevd):
            pydevd = PyDevdFixture(pydevd)
        self._pydevd = pydevd

        def highlevel_lifecycle(fix, _cls=vsc.LIFECYCLE):
            pydevd = PyDevdLifecycle(self._pydevd)
            return _cls(fix, pydevd, self.hidden)
        vsc.LIFECYCLE = highlevel_lifecycle

    def _new_fake_vsc(self, start_adapter=None, handler=None):
        if start_adapter is None:
            try:
                self._default_fake_vsc
            except AttributeError:
                pass
            else:
                raise RuntimeError('default fake VSC already created')
            start_adapter = self.debugger.start
        return self._new_vsc(start_adapter, handler)

    @property
    def vsc(self):
        return self._vsc.fake

    @property
    def vsc_msgs(self):
        return self._vsc.msgs

    @property
    def debugger(self):
        return self._pydevd.fake

    @property
    def debugger_msgs(self):
        return self._pydevd.msgs

    @property
    def lifecycle(self):
        return self._vsc.lifecycle

    @property
    def ishidden(self):
        return self._vsc.ishidden and self._pydevd.ishidden

    @contextlib.contextmanager
    def hidden(self):
        with self._vsc.hidden():
            with self._pydevd.hidden():
                yield

    def new_fake(self, debugger=None, handler=None):
        """Return a new fake VSC that may be used in tests."""
        if debugger is None:
            debugger = self._pydevd.new_fake()
        vsc = self._vsc.new_fake(debugger.start, handler)
        return vsc, debugger

    def assert_no_failures(self):
        self._vsc.assert_no_failures()
        self._pydevd.assert_no_failures()

    def reset(self):
        self._vsc.reset()
        self._debugger.reset()

    # wrappers

    def send_request(self, command, args=None, handle_response=None):
        return self._vsc.send_request(command, args, handle_response)

    @contextlib.contextmanager
    def wait_for_event(self, event, *args, **kwargs):
        with self._vsc.wait_for_event(event, *args, **kwargs):
            yield

    @contextlib.contextmanager
    def expect_debugger_command(self, cmdid):
        with self._pydevd.expected_command(cmdid):
            yield

    def set_debugger_response(self, cmdid, payload, **kwargs):
        self._pydevd.set_response(cmdid, payload, **kwargs)

    def send_debugger_event(self, cmdid, payload):
        self._pydevd.send_event(cmdid, payload)

    @contextlib.contextmanager
    def disconnect_when_done(self):
        with self._vsc.disconnect_when_done():
            yield

    # combinations

    def send_event(self, cmdid, text, event=None, handler=None):
        if event is not None:
            with self.wait_for_event(event, handler=handler):
                self.send_debugger_event(cmdid, text)
        else:
            self.send_debugger_event(cmdid, text)
            return None

    def set_threads(self, _thread, *threads, **kwargs):
        first = Thread.from_raw(_thread)
        threads = [first] + [Thread.from_raw(t) for t in threads]
        return self._set_threads(threads, **kwargs)

    def set_thread(self, thread):
        thread = Thread.from_raw(thread)
        threads = (thread,)
        return self._set_threads(threads)[thread]

    def _set_threads(self, threads, default_threads=True):
        # Set up and send messages.
        allthreads = self._pydevd.set_threads_response(
            threads,
            default_threads=default_threads,
        )
        ignored = ('ptvsd.', 'pydevd.')
        supported = [t for t in allthreads if not t.name.startswith(ignored)]
        with self._vsc._wait_for_events(['thread' for _ in supported]):
            self.send_request('threads')

        # Extract thread info from the response.
        request = {t.name: t for t in threads}
        response = {t: None for t in threads}
        for msg in reversed(self.vsc.received):
            if msg.type == 'response':
                if msg.command == 'threads':
                    break
        else:
            assert False, 'we waited for the response in send_request()'
        for tinfo in msg.body['threads']:
            try:
                thread = request[tinfo['name']]
            except KeyError:
                continue
            response[thread] = tinfo['id']
        return response

    def suspend(self, thread, reason, *stack):
        ptid, _ = thread
        with self.wait_for_event('stopped'):
            if isinstance(reason, Exception):
                exc = reason
                self._pydevd.send_caught_exception_events(thread, exc, *stack)
                self._pydevd.set_exception_var_response(exc)
            else:
                self._pydevd.send_suspend_event(thread, reason, *stack)

    def pause(self, thread, *stack):
        thread = Thread.from_raw(thread)
        tid = self.set_thread(thread)
        self._pydevd.send_pause_event(thread, *stack)
        if self._vsc._hidden:
            self._vsc.msgs.next_event()
        self.send_request('stackTrace', {'threadId': tid})
        self.send_request('scopes', {'frameId': 1})
        return tid

    def error(self, thread, exc, frame):
        thread = Thread.from_raw(thread)
        tid = self.set_thread(thread)
        self.suspend(thread, exc, frame)
        return tid


class VSCTest(object):
    """The base mixin class for high-level VSC-only ptvsd tests."""

    FIXTURE = VSCFixture

    fix = None  # overridden in setUp()

    @classmethod
    def _new_daemon(cls, *args, **kwargs):
        return cls.FIXTURE.FAKE(*args, **kwargs)

    def setUp(self):
        super(VSCTest, self).setUp()

        def new_daemon(*args, **kwargs):
            vsc = self._new_daemon(*args, **kwargs)
            self.addCleanup(vsc.close)
            return vsc
        self.fix = self.FIXTURE(new_daemon)

        self.maxDiff = None

    def __getattr__(self, name):
        return getattr(self.fix, name)

    @property
    def new_response(self):
        return self.fix.vsc_msgs.new_response

    @property
    def new_failure(self):
        return self.fix.vsc_msgs.new_failure

    @property
    def new_event(self):
        return self.fix.vsc_msgs.new_event

    def assert_vsc_received(self, received, expected):
        received = list(self.vsc.protocol.parse_each(received))
        expected = list(self.vsc.protocol.parse_each(expected))
        self.assertEqual(received, expected)

    def assert_vsc_failure(self, received, expected, req):
        received = list(self.vsc.protocol.parse_each(received))
        expected = list(self.vsc.protocol.parse_each(expected))
        self.assertEqual(received[:-1], expected)

        failure = received[-1]
        expected = self.vsc.protocol.parse(
            self.fix.vsc_msgs.new_failure(req, failure.message))
        self.assertEqual(failure, expected)

    def assert_received(self, daemon, expected):
        """Ensure that the received messages match the expected ones."""
        received = list(daemon.protocol.parse_each(daemon.received))
        expected = list(daemon.protocol.parse_each(expected))
        self.assertEqual(received, expected)


class HighlevelTest(VSCTest):
    """The base mixin class for high-level ptvsd tests."""

    FIXTURE = HighlevelFixture

    @classmethod
    def _new_daemon(cls, *args, **kwargs):
        return cls.FIXTURE.DAEMON(*args, **kwargs)

    @property
    def pydevd(self):
        return self.debugger

    def new_fake(self, debugger=None, handler=None):
        """Return a new fake VSC that may be used in tests."""
        vsc, debugger = self.fix.new_fake(debugger, handler)
        return vsc, debugger


class RunningTest(HighlevelTest):
    """The mixin class for high-level tests for post-start operations."""

    def launched(self, port, **kwargs):
        return self.lifecycle.launched(port=port, **kwargs)

    def attached(self, port, **kwargs):
        return self.lifecycle.attached(port=port, **kwargs)
