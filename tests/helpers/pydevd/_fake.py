import socket
import threading

from ptvsd.wrapper import start_server, start_client

from ._pydevd import parse_message, iter_messages, StreamFailure


def _connect(host, port):
    if host is None:
        return start_server(port)
    else:
        return start_client(host, port)


class FakePyDevd(object):
    """A testing double for PyDevd.

    Note that you have the option to provide a handler function.  This
    function will be called for each received message, with two args:
    the received message and the fake's "send_message" method.  If
    appropriate, it may call send_message() in response to the received
    message, along with doing anything else it needs to do.  Any
    exceptions raised by the handler are recorded but otherwise ignored.

    Example usage:

      >>> fake = FakePyDevd('127.0.0.1', 8888)
      >>> fake.start()
      >>> try:
      ...   fake.send_message(b'101\t1\t\n')
      ...   # wait for events...
      ... finally:
      ...   fake.close()
      >>> fake.assert_received(testcase, [
      ...   b'101\t1\t',  # the "run" response
      ...   # some other events
      ... ])

    A description of the protocol:
      https://github.com/fabioz/PyDev.Debugger/blob/master/_pydevd_bundle/pydevd_comm.py
    """  # noqa

    CONNECT = _connect

    def __init__(self, handler=None, connect=None):
        if connect is None:
            connect = self.CONNECT

        self._handler = handler
        self._connect = connect

        self._closed = False
        self._received = []
        self._failures = []

        # These are set when we start.
        self._host = None
        self._port = None
        self._sock = None
        self._listener = None

    def start(self, host, port):
        """Start the fake pydevd daemon.

        This calls the earlier provided connect() function.  By default
        this calls either start_server() or start_client() (depending on
        the host) from ptvsd.wrapper.  Thus the ptvsd message processor
        is started and a PydevdSocket is used as the connection.

        A listener loop is started in another thread to handle incoming
        messages from the socket (i.e. from ptvsd).
        """
        self._host = host or None
        self._port = port
        self._sock = self._connect(self._host, self._port)

        self._listener = threading.Thread(target=self._listen)
        self._listener.start()

    def send_message(self, msg):
        """Serialize the message to the line format and send it to ptvsd.

        If the message is bytes or a string then it is send as-is.
        """
        msg = parse_message(msg)
        raw = msg.as_bytes()
        if not raw.endswith(b'\n'):
            raw += b'\n'
        try:
            self._send(raw)
        except Exception as exc:
            failure = StreamFailure('send', msg, exc)
            self._failures.append(failure)

    def close(self):
        """If started, close the socket and wait for the listener to finish."""
        if self._closed:
            return

        self._closed = True
        if self._sock is not None:
            self._sock.shutdown(socket.SHUT_RDWR)
            self._sock.close()
            self._sock = None
        if self._listener is not None:
            self._listener.join()
            self._listener = None

    def assert_received(self, case, expected, nofailures=True):
        """Ensure that the received messages match the expected ones."""
        received = [parse_message(msg) for msg in self._received]
        expected = [parse_message(msg) for msg in expected]
        case.assertEqual(received, expected)
        if nofailures:
            case.assertFalse(self._failures)

    # internal methods

    def _listen(self):
        with self._sock.makefile('rb') as sockfile:
            # TODO: Support breaking the loop when closed.
            for msg in iter_messages(sockfile, lambda: self._closed):
                if isinstance(msg, StreamFailure):
                    self._failures.append(msg)
                else:
                    self._add_received(msg)

    def _add_received(self, msg):
        self._received.append(msg)

        if self._handler is not None:
            self._handler(msg, self.send_message)

    def _send(self, raw):
        while raw:
            sent = self._sock.send(raw)
            raw = raw[sent:]
