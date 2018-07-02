from __future__ import absolute_import, print_function

import contextlib
import json
import socket
import sys
import time
import threading
import warnings

from ptvsd._util import new_hidden_thread
from . import Closeable
from .message import (
    raw_read_all as read_messages,
    raw_write_one as write_message
)
from .socket import (
    Connection, create_server, create_client, close,
    recv_as_read, send_as_write,
    timeout as socket_timeout)
from .threading import get_locked_and_waiter
from .vsc import parse_message


class DebugSessionConnection(Closeable):

    VERBOSE = False
    #VERBOSE = True

    TIMEOUT = 1.0

    @classmethod
    def create_client(cls, addr, **kwargs):
        def connect(addr, timeout):
            sock = create_client()
            for _ in range(int(timeout * 10)):
                try:
                    sock.connect(addr)
                except (OSError, socket.error):
                    if cls.VERBOSE:
                        print('+', end='')
                        sys.stdout.flush()
                    time.sleep(0.1)
                else:
                    break
            else:
                raise RuntimeError('could not connect')
            return sock
        return cls._create(connect, addr, **kwargs)

    @classmethod
    def create_server(cls, addr, **kwargs):
        def connect(addr, timeout):
            server = create_server(addr)
            with socket_timeout(server, timeout):
                client, _ = server.accept()
            return Connection(client, server)
        return cls._create(connect, addr, **kwargs)

    @classmethod
    def _create(cls, connect, addr, timeout=None):
        if timeout is None:
            timeout = cls.TIMEOUT
        sock = connect(addr, timeout)
        if cls.VERBOSE:
            print('connected')
        self = cls(sock, ownsock=True)
        self._addr = addr
        return self

    def __init__(self, sock, ownsock=False):
        super(DebugSessionConnection, self).__init__()
        self._sock = sock
        self._ownsock = ownsock

    @property
    def is_client(self):
        try:
            return self._sock.server is None
        except AttributeError:
            return True

    def iter_messages(self):
        if self.closed:
            raise RuntimeError('connection closed')

        def stop():
            return self.closed
        read = recv_as_read(self._sock)
        for msg, _, _ in read_messages(read, stop=stop):
            if self.VERBOSE:
                print(repr(msg))
            yield parse_message(msg)

    def send(self, req):
        if self.closed:
            raise RuntimeError('connection closed')

        def stop():
            return self.closed
        write = send_as_write(self._sock)
        body = json.dumps(req)
        write_message(write, body, stop=stop)

    # internal methods

    def _close(self):
        if self._ownsock:
            close(self._sock)


class DebugSession(Closeable):

    VERBOSE = False
    #VERBOSE = True

    HOST = 'localhost'
    PORT = 8888

    TIMEOUT = None

    @classmethod
    def create_client(cls, addr=None, **kwargs):
        if addr is None:
            addr = (cls.HOST, cls.PORT)
        conn = DebugSessionConnection.create_client(
            addr,
            timeout=kwargs.get('timeout'),
        )
        return cls(conn, owned=True, **kwargs)

    @classmethod
    def create_server(cls, addr=None, **kwargs):
        if addr is None:
            addr = (cls.HOST, cls.PORT)
        conn = DebugSessionConnection.create_server(addr, **kwargs)
        return cls(conn, owned=True, **kwargs)

    def __init__(self, conn, seq=1000, handlers=(), timeout=None, owned=False):
        super(DebugSession, self).__init__()
        self._conn = conn
        self._seq = seq
        self._timeout = timeout
        self._owned = owned

        self._handlers = []
        for handler in handlers:
            if callable(handler):
                self._add_handler(handler)
            else:
                self._add_handler(*handler)
        self._received = []
        self._listenerthread = new_hidden_thread(
            target=self._listen,
            name='test.session',
        )
        self._listenerthread.start()

    @property
    def is_client(self):
        return self._conn.is_client

    @property
    def received(self):
        return list(self._received)

    def _create_request(self, command, **args):
        seq = self._seq
        self._seq += 1
        return {
            'type': 'request',
            'seq': seq,
            'command': command,
            'arguments': args,
        }

    def send_request(self, command, **args):
        if self.closed:
            raise RuntimeError('session closed')

        wait = args.pop('wait', False)
        req = self._create_request(command, **args)

        if wait:
            with self.wait_for_response(req) as resp:
                self._conn.send(req)
            resp_awaiter = AwaitableResponse(req, lambda: resp["msg"])
        else:
            resp_awaiter = self._get_awaiter_for_request(req, **args)
            self._conn.send(req)
        return resp_awaiter

    def add_handler(self, handler, **kwargs):
        if self.closed:
            raise RuntimeError('session closed')

        self._add_handler(handler, **kwargs)

    @contextlib.contextmanager
    def wait_for_event(self, event, **kwargs):
        if self.closed:
            raise RuntimeError('session closed')
        result = {'msg': None}

        def match(msg):
            result['msg'] = msg
            return msg.type == 'event' and msg.event == event
        handlername = 'event {!r}'.format(event)
        with self._wait_for_message(match, handlername, **kwargs):
            yield result

    def get_awaiter_for_event(self, event, condition=lambda msg: True, **kwargs): # noqa
        if self.closed:
            raise RuntimeError('session closed')
        result = {'msg': None}

        def match(msg):
            result['msg'] = msg
            return msg.type == 'event' and msg.event == event and condition(msg) # noqa
        handlername = 'event {!r}'.format(event)
        evt = self._get_message_handle(match, handlername)

        return AwaitableEvent(event, lambda: result["msg"], evt)

    def _get_awaiter_for_request(self, req, **kwargs):
        if self.closed:
            raise RuntimeError('session closed')

        try:
            command, seq = req.command, req.seq
        except AttributeError:
            command, seq = req['command'], req['seq']
        result = {'msg': None}

        def match(msg):
            if msg.type != 'response':
                return False
            result['msg'] = msg
            return msg.request_seq == seq
        handlername = 'response (cmd:{} seq:{})'.format(command, seq)
        evt = self._get_message_handle(match, handlername)

        return AwaitableResponse(req, lambda: result["msg"], evt)

    @contextlib.contextmanager
    def wait_for_response(self, req, **kwargs):
        if self.closed:
            raise RuntimeError('session closed')

        try:
            command, seq = req.command, req.seq
        except AttributeError:
            command, seq = req['command'], req['seq']
        result = {'msg': None}

        def match(msg):
            if msg.type != 'response':
                return False
            result['msg'] = msg
            return msg.request_seq == seq
        handlername = 'response (cmd:{} seq:{})'.format(command, seq)
        with self._wait_for_message(match, handlername, **kwargs):
            yield result

    # internal methods

    def _close(self):
        if self._owned:
            self._conn.close()
        if self._listenerthread != threading.current_thread():
            self._listenerthread.join(timeout=1.0)
            if self._listenerthread.is_alive():
                warnings.warn('session listener still running')
        self._check_handlers()

    def _listen(self):
        try:
            for msg in self._conn.iter_messages():
                if self.VERBOSE:
                    print(' ->', msg)
                self._receive_message(msg)
        except EOFError:
            self.close()

    def _receive_message(self, msg):
        for i, handler in enumerate(list(self._handlers)):
            handle_message, _, _ = handler
            handled = handle_message(msg)
            try:
                msg, handled = handled
            except TypeError:
                pass
            if handled:
                self._handlers.remove(handler)
                break
        self._received.append(msg)

    def _add_handler(self, handle_msg, handlername=None, required=True):
        self._handlers.append(
            (handle_msg, handlername, required))

    def _check_handlers(self):
        unhandled = []
        for handle_msg, name, required in self._handlers:
            if not required:
                continue
            unhandled.append(name or repr(handle_msg))
        if unhandled:
            raise RuntimeError('unhandled: {}'.format(unhandled))

    @contextlib.contextmanager
    def _wait_for_message(self, match, handlername, timeout=None):
        if timeout is None:
            timeout = self.TIMEOUT
        lock, wait = get_locked_and_waiter()

        def handler(msg):
            if not match(msg):
                return msg, False
            lock.release()
            return msg, True
        self._add_handler(handler, handlername)
        try:
            yield
        finally:
            wait(timeout or self._timeout, handlername, fail=True)

    def _get_message_handle(self, match, handlername):
        event = threading.Event()

        def handler(msg):
            if not match(msg):
                return msg, False
            event.set()
            return msg, True
        self._add_handler(handler, handlername, False)
        return event


class Awaitable(object):

    @classmethod
    def wait_all(cls, *awaitables):
        timeout = 3.0
        messages = []
        for _ in range(int(timeout * 10)):
            time.sleep(0.1)
            messages = []
            not_ready = (a for a in awaitables if a._event is not None and not a._event.is_set()) # noqa
            for awaitable in not_ready:
                if isinstance(awaitable, AwaitableEvent):
                    messages.append('Event {}'.format(awaitable.name))
                else:
                    messages.append('Response {}'.format(awaitable.name))
            if len(messages) == 0:
                return
        else:
            raise TimeoutError('Timeout waiting for {}'.format(','.join(messages))) # noqa

    def __init__(self, name, event=None):
        self._event = event
        self.name = name

    def wait(self, timeout=1.0):
        if self._event is None:
            return
        if not self._event.wait(timeout):
            message = 'Timeout waiting for '
            if isinstance(self, AwaitableEvent):
                message += 'Event {}'.format(self.name)
            else:
                message += 'Response {}'.format(self.name)
            raise TimeoutError(message)


class AwaitableResponse(Awaitable):

    def __init__(self, req, result_getter, event=None):
        super(AwaitableResponse, self).__init__(req["command"], event)
        self.req = req
        self._result_getter = result_getter

    @property
    def resp(self):
        return self._result_getter()


class AwaitableEvent(Awaitable):

    def __init__(self, name, result_getter, event=None):
        super(AwaitableEvent, self).__init__(name, event)
        self._result_getter = result_getter

    @property
    def event(self):
        return self._result_getter()
