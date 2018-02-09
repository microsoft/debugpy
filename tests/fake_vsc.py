import socket
import threading

from ._vsc import StreamFailure, encode_message, iter_messages, parse_message
from ._vsc import RawMessage  # noqa


class FakeVSC(object):
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
      >>> try:
      ...   fake.send_request('<a JSON message>')
      ...   # wait for events...
      ... finally:
      ...   fake.close()
      >>> fake.assert_received(testcase, [
      ...   # messages
      ... ])

    See debugger_protocol/messages/README.md for more about the
    protocol itself.
    """

    def __init__(self, start_adapter, handler=None):
        self._start_adapter = start_adapter
        self._handler = handler

        self._closed = False
        self._received = []
        self._failures = []

        # These are set when we start.
        self._host = None
        self._port = None
        self._adapter = None
        self._sock = None
        self._server = None
        self._listener = None

    @property
    def addr(self):
        host, port = self._host, self._port
        if host is None:
            host = '127.0.0.1'
        return (host, port)

    @property
    def received(self):
        """All the messages received thus far."""
        return list(self._received)

    @property
    def failures(self):
        """All send/recv failures thus far."""
        return self._sock.failures

    def start(self, host, port):
        """Start the fake and the adapter."""
        if self._closed or self._adapter is not None:
            raise RuntimeError('already started')

        if not host:
            host = None
            # The adapter is the server so start it first.
            self._adapter = self._start_adapter(host, port)
            self._start(host, port)
        else:
            # The adapter is the client so start it last.
            self._start(host, port)
            self._adapter = self._start_adapter(host, port)

    def send_request(self, req, delay=0.1):
        """Send the given Request object."""
        if self._closed:
            raise EOFError('closed')
        req = parse_message(req)
        raw = encode_message(req)
        try:
            self._send(raw)
        except Exception as exc:
            failure = ('send', req, exc)
            self._failures.append(failure)

    def close(self):
        """Close the fake's resources (e.g. socket, adapter)."""
        if self._closed:
            return

        self._closed = True
        self._close()

    # internal methods

    def _start(self, host, port):
        self._host = host
        self._port = port
        self._connect()

        self._listener = threading.Thread(target=self._listen)
        self._listener.start()

    def _connect(self):
        sock = socket.socket(
            socket.AF_INET,
            socket.SOCK_STREAM,
            socket.IPPROTO_TCP,
        )
        sock.setsockopt(
            socket.SOL_SOCKET,
            socket.SO_REUSEADDR,
            1,
        )
        if self._host is None:
            server = sock
            server.bind(self.addr)
            server.listen(1)
            sock, _ = server.accept()
        else:
            sock.connect(self.addr)
            server = None
        self._server = server
        self._sock = sock

    def _listen(self):
        with self._sock.makefile('rb') as sockfile:
            for msg in iter_messages(sockfile, lambda: self._closed):
                if isinstance(msg, StreamFailure):
                    self._failures.append(msg)
                else:
                    self._add_received(msg)

    def _add_received(self, msg):
        self._received.append(msg)

        if self._handler is not None:
            self._handler(msg, self.send_request)

    def _send(self, raw):
        while raw:
            sent = self._sock.send(raw)
            raw = raw[sent:]

    def _close(self):
        if self._adapter is not None:
            self._adapter.close()
            self._adapter = None
        if self._sock is not None:
            self._sock.shutdown(socket.SHUT_RDWR)
            self._sock.close()
            self._sock = None
        if self._server is not None:
            self._server.shutdown(socket.SHUT_RDWR)
            self._server.close()
            self._server = None
        if self._listener is not None:
            self._listener.join()
            self._listener = None
