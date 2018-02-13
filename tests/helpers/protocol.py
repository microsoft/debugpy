from collections import namedtuple
import threading

from . import socket


class StreamFailure(Exception):
    """Something went wrong while handling messages to/from a stream."""

    def __init__(self, direction, msg, exception):
        err = 'error while processing stream: {!r}'.format(exception)
        super(StreamFailure, self).__init__(self, err)
        self.direction = direction
        self.msg = msg
        self.exception = exception

    def __repr__(self):
        return '{}(direction={!r}, msg={!r}, exception={!r})'.format(
            type(self).__name__,
            self.direction,
            self.msg,
            self.exception,
        )


class MessageProtocol(namedtuple('Protocol', 'parse encode iter')):
    """A basic abstraction of a message protocol.

    parse(msg) - returns a message for the given data.
    encode(msg) - returns the message, serialized to the line-format.
    iter(stream, stop) - yield each message from the stream.  "stop"
        is a function called with no args which returns True if the
        iterator should stop.
    """

    def parse_each(self, messages):
        """Yield the parsed version of each message."""
        for msg in messages:
            yield self.parse(msg)


class Started(object):
    """A simple wrapper around a started message protocol daemon."""

    def __init__(self, fake):
        self.fake = fake

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def send_message(self, msg):
        return self.fake.send_response(msg)

    def close(self):
        self.fake.close()


class Daemon(object):
    """A testing double for a protocol daemon."""

    STARTED = Started

    @classmethod
    def validate_message(cls, msg):
        """Ensure the message is legitimate."""
        # By default check nothing.

    def __init__(self, connect, protocol, handler):
        self._connect = connect
        self._protocol = protocol

        self._closed = False
        self._received = []
        self._failures = []

        self._handlers = []
        self._default_handler = handler

        # These are set when we start.
        self._host = None
        self._port = None
        self._sock = None
        self._server = None
        self._listener = None

    @property
    def protocol(self):
        return self._protocol

    @property
    def received(self):
        """All the messages received thus far."""
        #parsed = self._protocol.parse_each(self._received)
        #return list(parsed)
        return list(self._received)

    @property
    def failures(self):
        """All send/recv failures thus far."""
        return list(self._failures)

    def start(self, host, port):
        """Start the fake daemon.

        This calls the earlier provided connect() function.

        A listener loop is started in another thread to handle incoming
        messages from the socket.
        """
        self._host = host or None
        self._port = port
        self._start()
        return self.STARTED(self)

    def send_message(self, msg):
        """Serialize msg to the line format and send it to the socket."""
        if self._closed:
            raise EOFError('closed')
        self._validate_message(msg)
        self._send_message(msg)

    def close(self):
        """Clean up the daemon's resources (e.g. sockets, files, listener)."""
        if self._closed:
            return

        self._closed = True
        self._close()

    def add_handler(self, handler, oneoff=True):
        """Add the given handler to the list of possible handlers."""
        entry = (handler, 1 if oneoff else None)
        self._handlers.append(entry)
        return handler

    def reset(self, force=False):
        """Clear the recorded messages."""
        if self._failures:
            raise RuntimeError('have failures ({!r})'.format(self._failures))
        if self._handlers:
            if force:
                self._handlers = []
            else:
                raise RuntimeError('have pending handlers')
        self._received = []

    # internal methods

    def _start(self, host=None):
        self._sock, self._server = self._connect(
            host or self._host,
            self._port,
        )

        # TODO: make it a daemon thread?
        self._listener = threading.Thread(target=self._listen)
        self._listener.start()

    def _listen(self):
        with self._sock.makefile('rb') as sockfile:
            for msg in self._protocol.iter(sockfile, lambda: self._closed):
                if isinstance(msg, StreamFailure):
                    self._failures.append(msg)
                else:
                    self._add_received(msg)

    def _add_received(self, msg):
        self._received.append(msg)
        self._handle_message(msg)

    def _handle_message(self, msg):
        for i, entry in enumerate(list(self._handlers)):
            handle_message, remaining = entry
            handled = handle_message(msg, self._send_message)
            if handled or handled is None:
                if remaining is not None:
                    if remaining == 1:
                        self._handlers.pop(i)
                    else:
                        self._handlers[i] = (handle_message, remaining-1)
                return handled
        else:
            if self._default_handler is not None:
                return self._default_handler(msg, self._send_message)
            return False

    def _validate_message(self, msg):
        return

    def _send_message(self, msg):
        msg = self._protocol.parse(msg)
        raw = self._protocol.encode(msg)
        try:
            self._send(raw)
        except Exception as exc:
            failure = StreamFailure('send', msg, exc)
            self._failures.append(failure)

    def _send(self, raw):
        while raw:
            sent = self._sock.send(raw)
            raw = raw[sent:]

    def _close(self):
        if self._sock is not None:
            socket.close(self._sock)
            self._sock = None
        if self._server is not None:
            socket.close(self._server)
            self._server = None
        if self._listener is not None:
            self._listener.join(timeout=1)
            # TODO: the listener isn't stopping!
            #if self._listener.is_alive():
            #    raise RuntimeError('timed out')
            self._listener = None
