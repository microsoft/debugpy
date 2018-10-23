from collections import namedtuple
import contextlib
import inspect
import platform
import time
import warnings

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
    CMD_GET_THREAD_STACK,
    CMD_GET_EXCEPTION_DETAILS,
    CMD_SUSPEND_ON_BREAKPOINT_EXCEPTION,
)

from ptvsd._util import new_hidden_thread
from tests.helpers.pydevd import FakePyDevd, PyDevdMessages
from tests.helpers.vsc import FakeVSC, VSCMessages

OS_ID = 'WINDOWS' if platform.system() == 'Windows' else 'UNIX'


@contextlib.contextmanager
def noop_cm(*args, **kwargs):
    yield


def _get_caller():
    caller = inspect.currentframe()
    filename = caller.f_code.co_filename
    while filename == __file__ or filename == contextlib.__file__:
        caller = caller.f_back
        filename = caller.f_code.co_filename
    return caller


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


class ThreadAlreadyExistsError(RuntimeError):
    pass


class Threads(object):

    MAIN = 'MainThread'

    def __init__(self):
        self._history = []
        self._alive = {}
        self._names = set()

        self._main = self.add(self.MAIN)

    def __repr__(self):
        return '<{}(alive={!r}, numkilled={!r})>'.format(
            type(self).__name__,
            self.alive,
            len(self._history) - len(self._alive),
        )

    @property
    def history(self):
        return list(self._history)

    @property
    def alive(self):
        return set(self._alive.values())

    @property
    def main(self):
        return self._main

    def add(self, name=None):
        tid = len(self._history) + 1
        if name and name in self._names:
            raise ThreadAlreadyExistsError(name)
        thread = Thread(tid, name)
        self._history.append(thread)
        self._alive[tid] = thread
        self._names.add(name)
        return thread

    def remove(self, thread):
        if not hasattr(thread, 'id'):
            thread = self._alive[thread]
        if thread.name == self.MAIN:
            raise RuntimeError('cannot remove main thread')
        self._remove(thread)
        return thread

    def _remove(self, thread):
        del self._alive[thread.id]
        self._names.remove(thread.name)

    def clear(self, keep=None):
        keep = {self.MAIN} | set(keep or ())
        for t in self.alive:
            if t.name not in keep:
                self._remove(t)


class PyDevdLifecycle(object):

    def __init__(self, fix):
        self._fix = fix

    @contextlib.contextmanager
    def _wait_for_initialized(self):
        with self._fix.wait_for_command(CMD_REDIRECT_OUTPUT):
            with self._fix.wait_for_command(CMD_SUSPEND_ON_BREAKPOINT_EXCEPTION):
                with self._fix.wait_for_command(CMD_RUN):
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
        self.requests = None

    @contextlib.contextmanager
    def daemon_running(self, port=None, hide=False, disconnect=True):
        with self._fix.hidden() if hide else noop_cm():
            daemon = self._start_daemon(port)
        try:
            yield
        finally:
            with self._fix.hidden() if hide else noop_cm():
                self._stop_daemon(daemon, disconnect=disconnect)

    @contextlib.contextmanager
    def launched(self, port=None, hide=False, disconnect=True, **kwargs):
        with self.daemon_running(port, hide=hide, disconnect=disconnect):
            self.launch(**kwargs)
            yield

    @contextlib.contextmanager
    def attached(self, port=None, hide=False, disconnect=True, **kwargs):
        with self.daemon_running(port, hide=hide, disconnect=disconnect):
            self.attach(**kwargs)
            yield

    def launch(self, **kwargs):
        """Initialize the debugger protocol and then launch."""
        with self._hidden():
            self._handshake('launch', **kwargs)

    def attach(self, **kwargs):
        """Initialize the debugger protocol and then attach."""
        with self._hidden():
            self._handshake('attach', **kwargs)

    def disconnect(self, exitcode=0, **reqargs):
        self._fix.daemon.exitcode = exitcode
        self._send_request('disconnect', reqargs)
        # TODO: wait for an exit event?
        # TODO: call self._fix.vsc.close()?

    # internal methods

    def _send_request(self, command, args=None, handle_response=None):
        if self.requests is None:
            return self._fix.send_request(command, args, handle_response)

        txn = [None, None]
        self.requests.append(txn)

        def handler(msg, send, _handle_resp=handle_response):
            txn[1] = msg
            if _handle_resp is not None:
                _handle_resp(msg, send)

        req = self._fix.send_request(command, args, handler)
        txn[0] = req
        return req

    def _start_daemon(self, port):
        if port is None:
            port = self.PORT
        addr = (None, port)
        with self._hidden():
            # Anything that gets sent in VSCodeMessageProcessor.__init__()
            # must be waited for here.
            # TODO: Is this necessary any more since we added the "readylock"?
            with self._fix.wait_for_event('output'):
                daemon = self._fix.fake.start(addr)
                daemon.wait_until_connected()
        return daemon

    def _stop_daemon(self, daemon, disconnect=True, timeout=10.0):
        # We must close ptvsd directly (rather than closing the external
        # socket (i.e. "daemon").  This is because cloing ptvsd blocks,
        # keeping us from sending the disconnect request we need to send
        # at the end.
        t = new_hidden_thread(
            target=self._fix.close_ptvsd,
            name='test.lifecycle',
        )
        #with self._fix.wait_for_events(['exited', 'terminated']):
        if True:
            # The thread runs close_ptvsd(), which sends the two
            # events and then waits for a "disconnect" request.  We send
            # that after we receive the events.
            t.start()
        if disconnect:
            self.disconnect()
        t.join(timeout)
        if t.isAlive():
            raise Exception(
                '_stop_daemon timed out after {} secs'.format(timeout))
        daemon.close()

    def _handshake(self, command, threadnames=None, config=None, requests=None,
                   default_threads=True, process=True, reset=True,
                   **kwargs):
        initargs = dict(
            kwargs.pop('initargs', None) or {},
            disconnect=kwargs.pop('disconnect', True),
        )

        with self._fix.wait_for_event('initialized'):
            self._initialize(**initargs)
            self._send_request(command, **kwargs)

        if threadnames:
            self._fix.set_threads(*threadnames,
                                  **dict(default_threads=default_threads))

        self._handle_config(**config or {})
        with self._wait_for_debugger_init():
            self._send_request('configurationDone')

        if process:
            with self._fix.wait_for_event('process'):
                with self._fix.wait_for_event('ptvsd_process'):
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
        self._send_request(
            'initialize',
            dict(self.MIN_INITIALIZE_ARGS, **reqargs),
            handle_response,
        )

    def _handle_config(self, breakpoints=None, excbreakpoints=None):
        for req in breakpoints or ():
            self._send_request(
                'setBreakpoints',
                self._parse_breakpoints(req),
            )
        for req in excbreakpoints or ():
            self._send_request(
                'setExceptionBreakpoints',
                self._parse_exception_breakpoints(req),
            )

    def _parse_breakpoints(self, req):
        # setBreakpoints request:
        #   source : <Source>
        #   ---
        #   breakpoints : [<SourceBreakpoint>]
        #   lines : [int]
        #   sourceModified : bool
        # <Source>:
        #   ---
        #   name : str
        #   path : str
        #   sourceReference : num
        #   presentationHint : enum
        #   origin : str
        #   sources : [<Source>]
        #   adapterData : *
        #   checksums : [<Checksum>]
        # <Checksum>:
        #   algorithm : enum
        #   checksum : str
        #   ---
        # <SourceBreakpoint>:
        #   line : int
        #   ---
        #   column : int
        #   condition : str
        #   hitCondition : str
        #   logMessage : str
        # TODO: validate?
        return req

    def _parse_exception_breakpoints(self, req):
        # setExceptionBreakpoints request:
        #   filters : [str]
        #   ---
        #   exceptionOptions : [<ExceptionOptions>]
        # <ExceptionOptions>:
        #   breakMode : enum
        #   ---
        #   path : [<ExceptionPathSegment>]
        # <ExceptionPathSegment>:
        #   names : [str]
        #   ---
        #   negate : bool
        # TODO: validate?
        return req


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
            # Uncomment the following 2 lines to see all messages.
            #self._fake.PRINT_SENT_MESSAGES = True
            #self._fake.PRINT_RECEIVED_MESSAGES = True
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

    def reset(self, **kwargs):
        self.assert_no_failures()
        self.fake.reset(**kwargs)


class PyDevdFixture(FixtureBase):
    """A test fixture for the PyDevd protocol."""

    FAKE = FakePyDevd
    MSGS = PyDevdMessages

    def __init__(self, new_fake=None):
        if new_fake is None:
            new_fake = self.FAKE
        super(PyDevdFixture, self).__init__(new_fake, self.MSGS)
        self._threads = Threads()

    @property
    def threads(self):
        return self._threads

    def notify_main_thread(self):
        self.send_event(
            CMD_THREAD_CREATE,
            self.msgs.format_threads(self._threads.main),
        )

    @contextlib.contextmanager
    def expect_command(self, cmdid):
        yield
        if self._hidden:
            self.msgs.next_request()

    @contextlib.contextmanager
    def wait_for_command(self, cmdid, *args, **kwargs):
        with self.fake.wait_for_command(cmdid, *args, **kwargs):
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

    def set_threads_response(self):
        text = self.msgs.format_threads(*self._threads.alive)
        self.set_response(CMD_RETURN, text, reqid=CMD_LIST_THREADS)

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

    def set_exception_var_response(self, threadid, exc, *frames):
        self.set_response(
            CMD_GET_EXCEPTION_DETAILS,
            self.msgs.format_exception_details(
                threadid, exc, *frames
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

    @property
    def daemon(self):
        # TODO: This is a horrendous use of internal details!
        return self.fake._adapter.daemon.binder.ptvsd

    @property
    def _proc(self):
        # This is used below in close_ptvsd().
        try:
            return self.daemon.proc
        except AttributeError:
            # TODO: Fall back to self.daemon.session._msgprocessor?
            return None

    def send_request(self, cmd, args=None, handle_response=None, timeout=1):
        kwargs = dict(args or {}, handler=handle_response)
        with self._wait_for_response(cmd, timeout=timeout, **kwargs) as req:
            self.fake.send_request(req)
        return req

    @contextlib.contextmanager
    def _wait_for_response(self, command, *args, **kwargs):
        handle = kwargs.pop('handler', None)
        timeout = kwargs.pop('timeout', 1)
        req = self.msgs.new_request(command, *args, **kwargs)
        with self.fake.wait_for_response(req, handler=handle, timeout=timeout):
            yield req
        if self._hidden:
            self.msgs.next_response()

    @contextlib.contextmanager
    def wait_for_event(self, event, *args, **kwargs):
        if 'caller' not in kwargs:
            caller = _get_caller()
            kwargs['caller'] = (caller.f_code.co_filename, caller.f_lineno)
        with self.fake.wait_for_event(event, *args, **kwargs):
            yield
        if self._hidden:
            self.msgs.next_event()

    @contextlib.contextmanager
    def wait_for_events(self, events):
        if not events:
            yield
            return
        with self.wait_for_events(events[1:]):
            with self.wait_for_event(events[0]):
                yield

    def get_threads(self, name='MainThread'):
        threads = {}

        def handle_response(msg, _):
            for t in msg.body['threads']:
                threads[t['id']] = t['name']
                if t['name'] == name:
                    threads[None] = t['id']

        self.send_request('threads', handle_response=handle_response)
        return threads, threads.pop(None)

    def close_ptvsd(self, exitcode=None):
        # TODO: Use the session instead.
        if self._proc is None:
            warnings.warn('"proc" not bound')
        else:
            self._proc.close()
        self.daemon.exitcode = exitcode
        self.daemon.close()


class HighlevelFixture(object):

    DAEMON = FakeVSC
    DEBUGGER = FakePyDevd

    DEFAULT_THREADS = [
        'ptvsd.Server',
        'pydevd.thread1',
        'pydevd.thread2',
    ]

    def __init__(self, vsc=None, pydevd=None, mainthread=True):
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

        self._default_threads = None
        self._known_threads = set()
        if mainthread:
            self._known_threads.add(self._pydevd.threads.main)

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
    def threads(self):
        return self._pydevd.threads

    @property
    def ishidden(self):
        return self._vsc.ishidden and self._pydevd.ishidden

    @property
    def daemon(self):
        return self._vsc.daemon

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

    def reset(self, **kwargs):
        self._vsc.reset(**kwargs)
        self._debugger.reset(**kwargs)

    # wrappers

    def set_default_threads(self):
        if self._default_threads is not None:
            return
        self._default_threads = {}
        for name in self.DEFAULT_THREADS:
            thread = self._pydevd.threads.add(name)
            self._default_threads[name] = thread

    def send_request(self, command, args=None, handle_response=None, **kwargs):
        return self._vsc.send_request(command, args, handle_response,
                                      **kwargs)

    @contextlib.contextmanager
    def wait_for_event(self, event, *args, **kwargs):
        with self._vsc.wait_for_event(event, *args, **kwargs):
            yield

    @contextlib.contextmanager
    def wait_for_events(self, events):
        with self._vsc.wait_for_events(events):
            yield

    @contextlib.contextmanager
    def expect_debugger_command(self, cmdid):
        with self._pydevd.expect_command(cmdid):
            yield

    def set_debugger_response(self, cmdid, payload, **kwargs):
        self._pydevd.set_response(cmdid, payload, **kwargs)

    def send_debugger_event(self, cmdid, payload):
        self._pydevd.send_event(cmdid, payload)

    def close_ptvsd(self, **kwargs):
        self._vsc.close_ptvsd(**kwargs)

    # combinations

    def send_event(self, cmdid, text, event=None, handler=None):
        if event is not None:
            with self.wait_for_event(event, handler=handler):
                self.send_debugger_event(cmdid, text)
        else:
            self.send_debugger_event(cmdid, text)
            return None

    def set_threads(self, _threadname, *threadnames, **kwargs):
        threadnames = (_threadname,) + threadnames
        return self._set_threads(threadnames, **kwargs)

    def set_thread(self, threadname):
        threadnames = (threadname,)
        return self._set_threads(threadnames)[0]

    def _set_threads(self, threadnames, default_threads=True):
        # Update the list of "alive" threads.
        self._pydevd.threads.clear(keep=self.DEFAULT_THREADS)
        if default_threads:
            self.set_default_threads()
        request = {}
        threads = []
        for i, name in enumerate(threadnames):
            thread = self._pydevd.threads.add(name)
            threads.append(thread)
            request[thread.name] = i
        ignored = ('ptvsd.', 'pydevd.')
        newthreads = [t
                      for t in self._pydevd.threads.alive
                      if not t.name.startswith(ignored) and
                      t not in self._known_threads]

        # Send and handle messages.
        self._pydevd.set_threads_response()
        with self.wait_for_events(['thread' for _ in newthreads]):
            self.send_request('threads')
        self._known_threads.update(newthreads)

        # Extract thread info from the response.
        for msg in reversed(self.vsc.received):
            if msg.type == 'response':
                if msg.command == 'threads':
                    break
        else:
            assert False, 'we waited for the response in send_request()'
        response = [(None, t) for t in threads]
        for tinfo in msg.body['threads']:
            try:
                i = request.pop(tinfo['name'])
            except KeyError:
                continue
            response[i] = (tinfo['id'], threads[i])
        return response

    def suspend(self, thread, reason, *stack):
        with self.wait_for_event('stopped'):
            if isinstance(reason, Exception):
                exc = reason
                self._pydevd.set_exception_var_response(thread.id, exc, *stack)
                self._pydevd.send_caught_exception_events(thread, exc, *stack)
            else:
                self._pydevd.send_suspend_event(thread, reason, *stack)

    def pause(self, threadname, *stack):
        tid, thread = self.set_thread(threadname)
        self._pydevd.send_pause_event(thread, *stack)
        if self._vsc._hidden:
            self._vsc.msgs.next_event()
        payload = self.debugger_msgs.format_frames(thread.id, 'pause', *stack)
        self.set_debugger_response(CMD_GET_THREAD_STACK, payload)
        self.send_request('stackTrace', {'threadId': tid})
        self.send_request('scopes', {'frameId': 1})
        return tid, thread

    def error(self, threadname, exc, frame):
        tid, thread = self.set_thread(threadname)
        self.suspend(thread, exc, frame)
        return tid, thread


class VSCTest(object):
    """The base mixin class for high-level VSC-only ptvsd tests."""

    FIXTURE = VSCFixture

    _ready = False
    _fix = None  # overridden in setUp()

    @classmethod
    def _new_daemon(cls, *args, **kwargs):
        return cls.FIXTURE.FAKE(*args, **kwargs)

    def setUp(self):
        super(VSCTest, self).setUp()
        self._ready = True

        self.maxDiff = None

    def __getattr__(self, name):
        if not self._ready:
            raise AttributeError
        return getattr(self.fix, name)

    @property
    def fix(self):
        if self._fix is None:

            def new_daemon(*args, **kwargs):
                vsc = self._new_daemon(*args, **kwargs)
                self.addCleanup(vsc.close)
                return vsc

            try:
                self._fix = self._new_fixture(new_daemon)
            except AttributeError:
                raise Exception
        return self._fix

    @property
    def new_response(self):
        return self.fix.vsc_msgs.new_response

    @property
    def new_failure(self):
        return self.fix.vsc_msgs.new_failure

    @property
    def new_event(self):
        return self.fix.vsc_msgs.new_event

    def _new_fixture(self, new_daemon):
        return self.FIXTURE(new_daemon)

    def assert_vsc_received(self, received, expected):
        from tests.helpers.message import assert_messages_equal

        received = list(self.vsc.protocol.parse_each(received))
        expected = list(self.vsc.protocol.parse_each(expected))
        assert_messages_equal(received, expected)

    def assert_vsc_failure(self, received, expected, req):
        received = list(self.vsc.protocol.parse_each(received))
        expected = list(self.vsc.protocol.parse_each(expected))
        self.assertEqual(received[:-1], expected)

        failure = received[-1] if len(received) > 0 else []
        if failure:
            expected = self.vsc.protocol.parse(
                self.fix.vsc_msgs.new_failure(req, failure.message))
        self.assertEqual(failure, expected)

    def assert_received(self, daemon, expected):
        """Ensure that the received messages match the expected ones."""
        received = list(daemon.protocol.parse_each(daemon.received))
        expected = list(daemon.protocol.parse_each(expected))
        self.assertEqual(received, expected)

    def assert_contains(self, received, expected, parser='vsc'):
        parser = self.vsc.protocol if parser == 'vsc' else parser
        from tests.helpers.message import assert_contains_messages
        received = list(parser.parse_each(received))
        expected = list(parser.parse_each(expected))
        assert_contains_messages(received, expected)

    def assert_received_unordered_payload(self, daemon, expected):
        """Ensure that the received messages match the expected ones
        regardless of payload order."""
        received = sorted(m.payload for m in
                          daemon.protocol.parse_each(daemon.received))
        expected = sorted(m.payload for m in
                          daemon.protocol.parse_each(expected))
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

    def wait_for_pydevd(self, *msgs, **kwargs):
        timeout = kwargs.pop('timeout', 10.0)
        assert not kwargs
        steps = int(timeout * 100) + 1
        for _ in range(steps):
            # TODO: Watch for the specific messages.
            if len(self.pydevd.received) >= len(msgs):
                break
            time.sleep(0.01)
        else:
            if len(self.pydevd.received) < len(msgs):
                raise RuntimeError('timed out')


class RunningTest(HighlevelTest):
    """The mixin class for high-level tests for post-start operations."""

    def launched(self, port, **kwargs):
        return self.lifecycle.launched(port=port, **kwargs)

    def attached(self, port, **kwargs):
        return self.lifecycle.attached(port=port, **kwargs)
