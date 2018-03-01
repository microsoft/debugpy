import contextlib
import threading

from tests.helpers import protocol, socket
from ._vsc import encode_message, iter_messages, parse_message


PROTOCOL = protocol.MessageProtocol(
    parse=parse_message,
    encode=encode_message,
    iter=iter_messages,
)


def _bind(address):
    connect, remote = socket.bind(address)

    def connect(_connect=connect):
        client, server = _connect()
        return socket.Connection(client, server)
    return connect, remote


class Started(protocol.Started):

    def send_request(self, msg):
        self.wait_until_connected()
        return self.fake.send_request(msg)


class FakeVSC(protocol.Daemon):
    """A testing double for a VSC debugger protocol client.

    This class facilitates sending VSC debugger protocol messages over
    the socket to ptvsd.  It also supports tracking (and even handling)
    the responses from ptvsd.

    "handler" is a function that reacts to incoming responses and events
    from ptvsd.  It takes a single response/event, along with a function
    for sending messages (requests, events) to ptvsd.

    Example usage:

      >>> pydevd = FakePyDevd()
      >>> fake = FakeVSC(lambda h, p: pydevd.start)
      >>> fake.start(None, 8888)
      >>> with fake.start(None, 8888):
      ...   fake.send_request('<a JSON message>')
      ...   # wait for events...
      ... 
      >>> fake.assert_received(testcase, [
      ...   # messages
      ... ])
      >>> 

    See debugger_protocol/messages/README.md for more about the
    protocol itself.
    """  # noqa

    STARTED = Started

    PROTOCOL = PROTOCOL

    def __init__(self, start_adapter, handler=None):
        super(FakeVSC, self).__init__(
            _bind,
            PROTOCOL,
            handler,
        )

        def start_adapter(address, start=start_adapter):
            self._adapter = start(address)
            return self._adapter
        self._start_adapter = start_adapter
        self._adapter = None

    def start(self, address):
        """Start the fake and the adapter."""
        if self._adapter is not None:
            raise RuntimeError('already started')
        return super(FakeVSC, self).start(address)

    def send_request(self, req):
        """Send the given Request object."""
        return self.send_message(req)

    def wait_for_response(self, req, **kwargs):
        reqseq = req['seq']
        command = req['command']

        def match(msg):
            #msg = parse_message(msg)
            try:
                actual = msg.request_seq
            except AttributeError:
                return False
            if actual != reqseq:
                return False
            assert(msg.command == command)
            return True

        return self._wait_for_message(match, req, **kwargs)

    def wait_for_event(self, event, **kwargs):
        def match(msg):
            #msg = parse_message(msg)
            try:
                actual = msg.event
            except AttributeError:
                return False
            if actual != event:
                return False
            return True

        return self._wait_for_message(match, req=None, **kwargs)

    # internal methods

    def _start(self, address):
        host, port = address
        if host is None:
            # The adapter is the server so start it first.
            adapter = self._start_adapter((None, port))
            return super(FakeVSC, self)._start(adapter.address)
        else:
            # The adapter is the client so start it last.
            # TODO: For now don't use this.
            raise NotImplementedError
            addr, starting = super(FakeVSC, self)._start(address)
            self._start_adapter(addr)
            # TODO Wait for adapter to be ready?
            return addr, starting

    def _close(self):
        if self._adapter is not None:
            self._adapter.close()
            self._adapter = None
        super(FakeVSC, self)._close()

    @contextlib.contextmanager
    def _wait_for_message(self, match, req=None, handler=None, timeout=1):
        lock = threading.Lock()
        lock.acquire()

        def handle_message(msg, send_message):
            if match(msg):
                lock.release()
                if handler is not None:
                    handler(msg, send_message)
            else:
                return False
        self.add_handler(handle_message)

        yield req

        lock.acquire(timeout=timeout)  # Wait for the message to match.
        lock.release()
