import contextlib
import itertools
import platform

from _pydevd_bundle.pydevd_comm import (
    CMD_VERSION,
    CMD_LIST_THREADS,
    CMD_THREAD_SUSPEND,
)

from tests.helpers.pydevd import FakePyDevd
from tests.helpers.vsc import FakeVSC


OS_ID = 'WINDOWS' if platform.system() == 'Windows' else 'UNIX'


class PyDevdMessages(object):

    protocol = FakePyDevd.PROTOCOL

    def __init__(self,
                 request_seq=1000000000,  # ptvsd requests to pydevd
                 response_seq=0,  # PyDevd responses/events to ptvsd
                 event_seq=None,
                 ):
        self.request_seq = itertools.count(request_seq)
        self.response_seq = itertools.count(response_seq)
        if event_seq is None:
            self.event_seq = self.response_seq
        else:
            self.event_seq = itertools.count(event_seq)

    def new_request(self, cmdid, *args, **kwargs):
        """Return a new PyDevd request message."""
        return self._new_message(cmdid, args=args, **kwargs)

    def new_response(self, req, *args):
        """Return a new VSC response message."""
        req = self.protocol.parse(req)
        return self._new_message(req.cmdid, req.seq, args)

    def new_event(self, cmdid, *args, **kwargs):
        """Return a new VSC event message."""
        return self._new_message(cmdid, args=args, **kwargs)

    def _new_message(self, cmdid, seq=None, args=()):
        if seq is None:
            seq = next(self.request_seq)
        text = '\t'.join(args)
        msg = (cmdid, seq, text)
        return self.protocol.parse(msg)

    def format_threads(self, *threads):
        text = '<xml>'
        for thread in threads:  # (tid, tname)
            text += '<thread id="{}" name="{}" />'.format(*thread)
        text += '</xml>'
        return text

    def format_frames(self, thread, reason, *frames):
        tid, _ = thread  # (tid, tname)
        text = '<xml>'
        text += '<thread id="{}" stop_reason="{}">'.format(tid, reason)
        fmt = '<frame id="{}" name="{}" file="{}" line="{}" />'
        for frame in frames:  # (fid, func, filename, line)
            text += fmt.format(*frame)
        text += '</thread>'
        text += '</xml>'
        return text


class VSCMessages(object):

    protocol = FakeVSC.PROTOCOL

    def __init__(self,
                 request_seq=0,  # VSC requests to ptvsd
                 response_seq=0,  # ptvsd responses/events to VSC
                 event_seq=None,
                 ):
        self.request_seq = itertools.count(request_seq)
        self.response_seq = itertools.count(response_seq)
        if event_seq is None:
            self.event_seq = self.response_seq
        else:
            self.event_seq = itertools.count(event_seq)

    def new_request(self, command, seq=None, **args):
        """Return a new VSC request message."""
        if seq is None:
            seq = next(self.request_seq)
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
            seq = next(self.response_seq)
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
            seq = next(self.event_seq)
        return {
            'type': 'event',
            'seq': seq,
            'event': eventname,
            'body': body,
        }


class VSCLifecycle(object):

    PORT = 8888

    MIN_INITIALIZE_ARGS = {
        'adapterID': '<an adapter ID>',
    }

    def __init__(self, fix):
        self._fix = fix

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
        with self._fix.hidden():
            self._handshake('launch', **kwargs)

    def attach(self, **kwargs):
        """Initialize the debugger protocol and then attach."""
        with self._fix.hidden():
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
        with self._fix.vsc.start(addr):
            with self._fix.disconnect_when_done():
                start()
                yield

    def _handshake(self, command, threads=None, config=None,
                   default_threads=True, reset=True,
                   **kwargs):
        initargs = dict(
            kwargs.pop('initargs', None) or {},
            disconnect=kwargs.pop('disconnect', True),
        )
        with self._fix.wait_for_event('initialized'):
            self._initialize(**initargs)
            self._fix.send_request(command, **kwargs)

        self._fix.set_threads(*threads or (),
                              **dict(default_threads=default_threads))

        self._handle_config(**config or {})
        with self._fix.wait_for_event('process'):
            self._fix.send_request('configurationDone')
        next(self._fix.debugger_msgs.request_seq)  # CMD_RUN

        if reset:
            self._fix.reset()
        else:
            self._fix.assert_no_failures()

    def _initialize(self, **reqargs):
        """
        See https://code.visualstudio.com/docs/extensionAPI/api-debugging#_the-vs-code-debug-protocol-in-a-nutshell
        """  # noqa
        def handle_response(resp, _):
            self._capabilities = resp.data['body']
        version = self._fix.debugger.VERSION
        self._fix.set_debugger_response(CMD_VERSION, version)
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


class HighlevelFixture(object):

    DAEMON = FakeVSC
    DEBUGGER = FakePyDevd

    def __init__(self, new_daemon=None, new_debugger=None):
        if new_daemon is None:
            new_daemon = self.DAEMON
        if new_debugger is None:
            new_debugger = self.DEBUGGER

        self._new_daemon = new_daemon
        self._new_debugger = new_debugger
        self.vsc_msgs = VSCMessages()
        self.debugger_msgs = PyDevdMessages()

        self._hidden = False

    @property
    def vsc(self):
        try:
            return self._vsc
        except AttributeError:
            self._vsc, self._debugger = self.new_fake()
            return self._vsc

    @property
    def debugger(self):
        try:
            return self._debugger
        except AttributeError:
            self._vsc, self._debugger = self.new_fake()
            return self._debugger

    @property
    def lifecycle(self):
        try:
            return self._lifecycle
        except AttributeError:
            self._lifecycle = VSCLifecycle(self)
            return self._lifecycle

    @contextlib.contextmanager
    def hidden(self):
        vsc = self.vsc.received
        debugger = self.debugger.received
        self._hidden = True
        try:
            yield
        finally:
            self._hidden = False
            self.vsc.reset(*vsc)
            self.debugger.reset(*debugger)

    def new_fake(self, debugger=None, handler=None):
        """Return a new fake VSC that may be used in tests."""
        if debugger is None:
            debugger = self._new_debugger()
        vsc = self._new_daemon(debugger.start, handler)
        return vsc, debugger

    def send_request(self, command, args=None, handle_response=None):
        kwargs = dict(args or {}, handler=handle_response)
        with self._wait_for_response(command, **kwargs) as req:
            self.vsc.send_request(req)
        return req

    @contextlib.contextmanager
    def _wait_for_response(self, command, *args, **kwargs):
        handler = kwargs.pop('handler', None)
        req = self.vsc_msgs.new_request(command, *args, **kwargs)
        with self.vsc.wait_for_response(req, handler=handler):
            yield req
        if self._hidden:
            next(self.vsc_msgs.response_seq)

    @contextlib.contextmanager
    def wait_for_event(self, event, *args, **kwargs):
        with self.vsc.wait_for_event(event, *args, **kwargs):
            yield
        if self._hidden:
            next(self.vsc_msgs.event_seq)

    def set_debugger_response(self, cmdid, payload):
        self.debugger.add_pending_response(cmdid, payload)
        if self._hidden:
            next(self.debugger_msgs.request_seq)

    def send_debugger_event(self, cmdid, payload):
        event = self.debugger_msgs.new_event(cmdid, payload)
        self.debugger.send_event(event)

    def set_threads(self, *threads, **kwargs):
        return self._set_threads(threads, **kwargs)

    def _set_threads(self, threads, default_threads=True):
        request = {t[1]: t for t in threads}
        response = {t: None for t in threads}
        if default_threads:
            threads = self._add_default_threads(threads)
        text = self.debugger_msgs.format_threads(*threads)
        self.set_debugger_response(CMD_LIST_THREADS, text)
        self.send_request('threads')

        for tinfo in self.vsc.received[-1].data['body']['threads']:
            try:
                thread = request[tinfo['name']]
            except KeyError:
                continue
            response[thread] = tinfo['id']
        return response

    def _add_default_threads(self, threads):
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
            thread = tid, tname
            allthreads.append(thread)
        allthreads.extend(threads)
        return allthreads

    def suspend(self, thread, reason, *stack):
        with self.wait_for_event('stopped'):
            self.send_debugger_event(
                CMD_THREAD_SUSPEND,
                self.debugger_msgs.format_frames(thread, reason, *stack),
            )

    #def set_variables(self, ...):
    #    ...

    @contextlib.contextmanager
    def disconnect_when_done(self):
        try:
            yield
        finally:
            self.send_request('disconnect')

    def assert_no_failures(self):
        assert self.vsc.failures == [], self.vsc.failures
        assert self.debugger.failures == [], self.debugger.failures

    def reset(self):
        self.assert_no_failures()
        self.vsc.reset()
        self.debugger.reset()


class HighlevelTest(object):
    """The base mixin class for high-level ptvsd tests."""

    FIXTURE = HighlevelFixture

    fix = None  # overridden in setUp()

    def setUp(self):
        super(HighlevelTest, self).setUp()

        def new_daemon(*args, **kwargs):
            vsc = self.FIXTURE.DAEMON(*args, **kwargs)
            self.addCleanup(vsc.close)
            return vsc
        self.fix = self.FIXTURE(new_daemon)

        self.maxDiff = None

    def __getattr__(self, name):
        return getattr(self.fix, name)

    @property
    def pydevd(self):
        return self.debugger

    @property
    def new_response(self):
        return self.fix.vsc_msgs.new_response

    @property
    def new_event(self):
        return self.fix.vsc_msgs.new_event

    def new_fake(self, debugger=None, handler=None):
        """Return a new fake VSC that may be used in tests."""
        vsc, debugger = self.fix.new_fake(debugger, handler)
        return vsc, debugger

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
            self.fix.vsc_msgs.new_failure(req, failure.data['message']))
        self.assertEqual(failure, expected)

    def assert_received(self, daemon, expected):
        """Ensure that the received messages match the expected ones."""
        received = list(daemon.protocol.parse_each(daemon.received))
        expected = list(daemon.protocol.parse_each(expected))
        self.assertEqual(received, expected)


class RunningTest(HighlevelTest):
    """The mixin class for high-level tests for post-start operations."""

    def launched(self, port, **kwargs):
        return self.lifecycle.launched(port=port, **kwargs)

    def attached(self, port, **kwargs):
        return self.lifecycle.attached(port=port, **kwargs)
