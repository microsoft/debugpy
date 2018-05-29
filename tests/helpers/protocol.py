from __future__ import absolute_import

from collections import namedtuple
import contextlib
import errno
import threading
import warnings

from . import socket
from .counter import Counter
from .threading import acquire_with_timeout


try:
    BrokenPipeError
except NameError:
    class BrokenPipeError(Exception):
        pass


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


class MessageCounters(namedtuple('MessageCounters',
                                 'request response event')):
    """Track the next "seq" value for the protocol message types."""

    REQUEST_INC = 1
    RESPONSE_INC = 1
    EVENT_INC = 1

    def __new__(cls, request=0, response=0, event=None):
        request = Counter(request, cls.REQUEST_INC)
        if response is None:
            response = request
        else:
            response = Counter(response, cls.RESPONSE_INC)
        if event is None:
            event = response
        else:
            event = Counter(event, cls.EVENT_INC)
        self = super(MessageCounters, cls).__new__(
            cls,
            request,
            response,
            event,
        )
        return self

    def next_request(self):
        return next(self.request)

    def next_response(self):
        return next(self.response)

    def next_event(self):
        return next(self.event)

    def reset(self, request=None, response=None, event=None):
        if request is None and response is None and event is None:
            raise ValueError('missing at least one counter')
        if request is not None:
            self.request.reset(start=request)
        if response is not None:
            self.response.reset(start=response)
        if event is not None:
            self.event.reset(start=event)

    def reset_all(self, start=0):
        self.request.reset(start)
        self.response.reset(start)
        self.event.reset(start)


class DaemonStarted(object):
    """A simple wrapper around a started protocol daemon."""

    def __init__(self, daemon, address, starting=None):
        self.daemon = daemon
        self.address = address
        self._starting = starting

    def __enter__(self):
        self.wait_until_connected()
        return self

    def __exit__(self, *args):
        self.close()

    def wait_until_connected(self, timeout=None):
        starting = self._starting
        if starting is None:
            return
        starting.join(timeout=timeout)
        if starting.is_alive():
            raise RuntimeError('timed out')
        self._starting = None

    def close(self):
        self.wait_until_connected()
        self.daemon.close()


class Daemon(object):

    STARTED = DaemonStarted

    def __init__(self, bind):
        self._bind = bind

        self._closed = False

        # These are set when we start.
        self._address = None
        self._sock = None

    def start(self, address):
        """Start the fake daemon.

        This calls the earlier provided bind() function.

        A listener loop is started in another thread to handle incoming
        messages from the socket.
        """
        self._address = address
        addr, starting = self._start(address)
        return self.STARTED(self, addr, starting)

    def close(self):
        """Clean up the daemon's resources (e.g. sockets, files, listener)."""
        if self._closed:
            return

        self._closed = True
        self._close()

    # internal methods

    def _start(self, address):
        connect, addr = self._bind(address)

        def run():
            self._sock = connect()
            self._handle_connected()
        t = threading.Thread(target=run)
        t.start()
        return addr, t

    def _handle_connected(self):
        pass

    def _close(self):
        if self._sock is not None:
            socket.close(self._sock)
            self._sock = None


class MessageDaemonStarted(DaemonStarted):
    """A simple wrapper around a started message protocol daemon."""

    def send_message(self, msg):
        self.wait_until_connected()
        return self.daemon.send_message(msg)


class MessageDaemon(Daemon):
    """A testing double for a protocol daemon."""

    STARTED = MessageDaemonStarted

    EXTERNAL = None
    PRINT_SENT_MESSAGES = False
    PRINT_RECEIVED_MESSAGES = False

    @classmethod
    def validate_message(cls, msg):
        """Ensure the message is legitimate."""
        # By default check nothing.

    def __init__(self, bind, protocol, handler):
        super(MessageDaemon, self).__init__(bind)

        self._protocol = protocol

        self._received = []
        self._failures = []

        self._handlers = []
        self._default_handler = handler

        # These are set when we start.
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

    def send_message(self, msg):
        """Serialize msg to the line format and send it to the socket."""
        if self._closed:
            raise EOFError('closed')
        self._validate_message(msg)
        self._send_message(msg)

    def add_handler(self, handler, handlername=None, caller=None, oneoff=True):
        """Add the given handler to the list of possible handlers."""
        entry = (
            handler,
            handlername or repr(handler),
            caller,
            1 if oneoff else None,
        )
        self._handlers.append(entry)
        return handler

    @contextlib.contextmanager
    def wait_for_message(self, match, req=None, handler=None,
                         handlername=None, caller=None, timeout=1):
        """Return a context manager that will wait for a matching message."""
        lock = threading.Lock()
        lock.acquire()

        def handle_message(msg, send_message):
            if not match(msg):
                return False
            lock.release()
            if handler is not None:
                handler(msg, send_message)
            return True
        self.add_handler(handle_message, handlername, caller)

        yield req

        # Wait for the message to match.
        if acquire_with_timeout(lock, timeout=timeout):
            lock.release()
        else:
            msg = 'timed out after {} seconds waiting for message ({})'
            warnings.warn(msg.format(timeout, handlername))

    def reset(self, *initial, **kwargs):
        """Clear the recorded messages."""
        self._reset(initial, **kwargs)

    # internal methods

    def _handle_connected(self):
        # TODO: make it a daemon thread?
        self._listener = threading.Thread(target=self._listen)
        self._listener.start()

    def _listen(self):
        try:
            with contextlib.closing(self._sock.makefile('rb')) as sockfile:
                for msg in self._protocol.iter(sockfile, lambda: self._closed):
                    if isinstance(msg, StreamFailure):
                        self._failures.append(msg)
                    else:
                        self._add_received(msg)
        except BrokenPipeError:
            if self._closed:
                return
            # TODO: try reconnecting?
            raise
        except OSError as exc:
            if exc.errno in (errno.EPIPE, errno.ESHUTDOWN):  # BrokenPipeError
                return
            if exc.errno == 9:  # socket closed
                return
            if exc.errno == errno.EBADF:  # socket closed
                return
            # TODO: try reconnecting?
            raise

    def _add_received(self, msg):
        if self.PRINT_RECEIVED_MESSAGES:
            print('<--' if self.EXTERNAL else '-->', msg)
        self._received.append(msg)
        self._handle_message(msg)

    def _handle_message(self, msg):
        for i, entry in enumerate(list(self._handlers)):
            handle_msg, name, caller, remaining = entry
            handled = handle_msg(msg, self._send_message)
            if handled or handled is None:
                if remaining is not None:
                    if remaining == 1:
                        self._handlers.pop(i)
                    else:
                        self._handlers[i] = (handle_msg, name, caller,
                                             remaining-1)
                return handled
        else:
            if self._default_handler is not None:
                return self._default_handler(msg, self._send_message)
            return False

    def _validate_message(self, msg):
        return

    def _send_message(self, msg):
        if self.PRINT_SENT_MESSAGES:
            print('-->' if self.EXTERNAL else '<--', msg)
        msg = self._protocol.parse(msg)
        raw = self._protocol.encode(msg)
        try:
            self._send(raw)
        except Exception as exc:
            raise
            failure = StreamFailure('send', msg, exc)
            self._failures.append(failure)

    def _send(self, raw):
        while raw:
            sent = self._sock.send(raw)
            raw = raw[sent:]

    def _close(self):
        super(MessageDaemon, self)._close()
        if self._listener is not None:
            self._listener.join(timeout=1)
            # TODO: the listener isn't stopping!
            #if self._listener.is_alive():
            #    raise RuntimeError('timed out')
            self._listener = None

    def _reset(self, initial, force=False):
        if self._failures:
            raise RuntimeError('have failures ({!r})'.format(self._failures))
        if self._handlers:
            if force:
                self._handlers = []
            else:
                names = []
                for _, name, caller, _ in self._handlers:
                    if caller:
                        try:
                            filename, lineno = caller
                        except (ValueError, TypeError):
                            # TODO: Support str, tracebacks?
                            raise NotImplementedError
                        else:
                            caller = '{}, line {}'.format(filename, lineno)
                        names.append('{} ({})'.format(name, caller))

                    else:
                        names.append(name)
                names = ', '.join(names)
                raise RuntimeError('have pending handlers: [{}]'.format(names))
        self._received = list(self._protocol.parse_each(initial))
