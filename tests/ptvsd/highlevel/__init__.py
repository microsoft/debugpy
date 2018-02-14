import contextlib
import itertools
import platform

from _pydevd_bundle.pydevd_comm import (
    CMD_RUN,
    CMD_VERSION,
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
        return self._new_response(req, err, body)

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

    MIN_INITIALIZE_ARGS = {
        'adapterID': '<an adapter ID>',
    }

    def __init__(self, fix):
        self._fix = fix

    def launched(self, port=8888, **kwargs):
        def start():
            self.launch(**kwargs)
        return self._started(start, port)

    def attached(self, port=8888, **kwargs):
        def start():
            self.attach(**kwargs)
        return self._started(start, port)

    def launch(self, **kwargs):
        """Initialize the debugger protocol and then launch."""
        self._handshake('launch', **kwargs)

    def attach(self, **kwargs):
        """Initialize the debugger protocol and then attach."""
        self._handshake('attach', **kwargs)

    def disconnect(self, **reqargs):
        self._send_request('disconnect', reqargs)
        # TODO: wait for an exit event?
        # TODO: call self._fix.vsc.close()?

    # internal methods

    @contextlib.contextmanager
    def _started(self, start, port):
        with self._fix.vsc.start(None, port):
            with self._fix.disconnect_when_done():
                start()
                yield

    def _handshake(self, command, config=None, reset=True, **kwargs):
        initargs = dict(
            kwargs.pop('initargs', None) or {},
            disconnect=kwargs.pop('disconnect', True),
        )
        with self._fix.vsc.wait_for_event('initialized'):
            self._initialize(**initargs)
            self._send_request(command, **kwargs)
        next(self._fix.vsc_msgs.event_seq)

        self._handle_config(**config or {})
        self._set_debugger_response(CMD_RUN, '')
        self._send_request('configurationDone')
        next(self._fix.vsc_msgs.event_seq)

        assert(self._fix.vsc.failures == [])
        assert(self._fix.debugger.failures == [])
        if reset:
            self._fix.vsc.reset()
            self._fix.debugger.reset()

    def _initialize(self, **reqargs):
        """
        See https://code.visualstudio.com/docs/extensionAPI/api-debugging#_the-vs-code-debug-protocol-in-a-nutshell
        """  # noqa
        def handle_response(resp, _):
            self._capabilities = resp.data['body']
        version = self._fix.debugger.VERSION
        self._set_debugger_response(CMD_VERSION, version)
        self._send_request(
            'initialize',
            dict(self.MIN_INITIALIZE_ARGS, **reqargs),
            handle_response,
        )

    def _handle_config(self, breakpoints=None, excbreakpoints=None):
        if breakpoints:
            self._send_request(
                'setBreakpoints',
                self._parse_breakpoints(breakpoints),
            )
        if excbreakpoints:
            self._send_request(
                'setExceptionBreakpoints',
                self._parse_breakpoints(excbreakpoints),
            )

    def _parse_breakpoints(self, breakpoints):
        for bp in breakpoints or ():
            raise NotImplementedError

    def _send_request(self, *args, **kwargs):
        self._fix.send_request(*args, **kwargs)
        next(self._fix.vsc_msgs.response_seq)

    def _set_debugger_response(self, *args, **kwargs):
        self._fix.set_debugger_response(*args, **kwargs)
        next(self._fix.debugger_msgs.request_seq)


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

    def new_fake(self, debugger=None, handler=None):
        """Return a new fake VSC that may be used in tests."""
        if debugger is None:
            debugger = self._new_debugger()
        vsc = self._new_daemon(debugger.start, handler)
        return vsc, debugger

    def send_request(self, command, args=None, handle_response=None):
        req = self.vsc_msgs.new_request(command, **args or {})
        with self.vsc.wait_for_response(req, handler=handle_response):
            self.vsc.send_request(req)
        return req

    def set_debugger_response(self, cmdid, payload):
        self.debugger.add_pending_response(cmdid, payload)

    @contextlib.contextmanager
    def disconnect_when_done(self):
        try:
            yield
        finally:
            self.send_request('disconnect')
            #self.vsc._received.pop(-1)


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
