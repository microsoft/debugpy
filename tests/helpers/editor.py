from __future__ import absolute_import

import contextlib
import json
import subprocess
import sys
import threading
import time

from . import Closeable
from .message import (
    raw_read_all as read_messages,
    raw_write_one as write_message
)
from .socket import create_client, close, recv_as_read, send_as_write
from .threading import get_locked_and_waiter
from .vsc import parse_message


class DebugSessionConnection(Closeable):

    VERBOSE = False

    @classmethod
    def create(cls, addr, timeout=2.0):
        sock = create_client()
        for _ in range(int(timeout * 10)):
            try:
                sock.connect(addr)
            except OSError:
                if cls.VERBOSE:
                    print('+', end='')
                sys.stdout.flush()
                time.sleep(0.1)
            else:
                break
        else:
            raise RuntimeError('could not connect')
        if cls.VERBOSE:
            print('connected')
        self = cls(sock, ownsock=True)
        self._addr = addr
        return self

    def __init__(self, sock, ownsock=False):
        super(DebugSessionConnection, self).__init__()
        self._sock = sock
        self._ownsock = ownsock

    def iter_messages(self):
        def stop():
            return self.closed
        read = recv_as_read(self._sock)
        for msg, _, _ in read_messages(read, stop=stop):
            if self.VERBOSE:
                print(msg)
            yield parse_message(msg)

    def send(self, req):
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

    @classmethod
    def create(cls, addr=('localhost', 8888), **kwargs):
        conn = DebugSessionConnection.create(addr)
        return cls(conn, owned=True, **kwargs)

    def __init__(self, conn, seq=1000, handlers=(), owned=False):
        super(DebugSession, self).__init__()
        self._conn = conn
        self._seq = seq
        self._owned = owned

        self._handlers = []
        for handler in handlers:
            if callable(handler):
                self._add_handler(handler)
            else:
                self._add_handler(*handler)
        self._received = []
        self._listenerthread = threading.Thread(target=self._listen)
        self._listenerthread.start()

    @property
    def received(self):
        return list(self._received)

    def send_request(self, command, **args):
        wait = args.pop('wait', True)
        seq = self._seq
        self._seq += 1
        req = {
            'type': 'request',
            'seq': seq,
            'command': command,
            'arguments': args,
        }
        if wait:
            with self.wait_for_response(req):
                self._conn.send(req)
        else:
            self._conn.send(req)
        return req

    def add_handler(self, handler, **kwargs):
        self._add_handler(handler, **kwargs)

    @contextlib.contextmanager
    def wait_for_event(self, event, **kwargs):
        def match(msg):
            return msg.type == 'event' and msg.event == event
        handlername = 'event {!r}'.format(event)
        with self._wait_for_message(match, handlername, **kwargs):
            yield

    @contextlib.contextmanager
    def wait_for_response(self, req, **kwargs):
        def match(msg):
            if msg.type != 'response':
                return False
            return msg.requestSeq == req.seq
        handlername = 'response ({} {})'.format(req.command, req.seq)
        with self._wait_for_message(match, handlername, **kwargs):
            yield

    # internal methods

    def _close(self):
        if self._owned:
            self._conn.close()
        self._listenerthread.join()  # TODO: timeout
        self._check_handlers()

    def _listen(self):
        try:
            for msg in self._conn.iter_messages():
                if self.VERBOSE:
                    print('received', msg)
                self._receive_message(msg)
        except EOFError:
            self.close()

    def _receive_message(self, msg):
        for i, handler in enumerate(list(self._handlers)):
            handle_message, _, _ = handler
            handled = handle_message(msg)
            if handled:
                try:
                    msg, handled = handled
                except TypeError:
                    pass
                del self._handlers[i]
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
            return
            raise RuntimeError('unhandled: {}'.format(unhandled))

    @contextlib.contextmanager
    def _wait_for_message(self, match, handlername, timeout=1.0):
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
            wait(timeout, handlername)


class DebugAdapter(Closeable):

    VERBOSE = False

    @classmethod
    def for_script(cls, filename, *argv, **kwargs):
        argv = [
            filename,
        ] + list(argv)
        return cls.start(argv, **kwargs)

    @classmethod
    def for_module(cls, module, *argv, **kwargs):
        argv = [
            '-m', module,
        ] + list(argv)
        return cls.start(argv, **kwargs)

    @classmethod
    def start(cls, argv, host='localhost', port=8888):
        addr = (host, port)
        argv = list(argv)
        if host and host not in ('localhost', '127.0.0.1'):
            argv.insert(0, host)
            argv.insert(0, '--host')
        if '--port' not in argv:
            argv.insert(0, str(port))
            argv.insert(0, '--port')
        proc = cls._start(argv)
        return cls(proc, addr, owned=True)

    @classmethod
    def _start(cls, argv):
        argv = [
            sys.executable,
            '-m', 'ptvsd',
        ] + argv
        proc = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        return proc

    def __init__(self, proc, addr, owned=False):
        super(DebugAdapter, self).__init__()
        self._proc = proc
        self._addr = addr
        self._session = None

    @property
    def output(self):
        return self._proc.stdout.read()

    def attach(self, **kwargs):
        if self._session is not None:
            raise RuntimeError('already attached')
        self._session = DebugSession.create(self._addr, **kwargs)
        return self._session

    def detach(self):
        if self._session is None:
            raise RuntimeError('not attached')
        session = self._session
        session.close()
        self._session = None
        return session.received

    def wait(self):
        self._proc.wait()

    # internal methods

    def _close(self):
        if self._session is not None:
            self._session.close()
        if self._proc is not None:
            self._proc.kill()
        if self.VERBOSE:
            lines = self.output.decode('utf-8').splitlines()
            print(' + ' + '\n + '.join(lines))


class FakeEditor(Closeable):

    def __init__(self, port=8888):
        super(FakeEditor, self).__init__()
        self._port = port
        self._adapter = None

    def start_debugger(self, argv):
        if self._adapter is not None:
            raise RuntimeError('debugger already running')
        self._adapter = DebugAdapter.start(argv, port=self._port)

    def launch_script(self, filename, *argv, **kwargs):
        if self._adapter is not None:
            raise RuntimeError('debugger already running')
        self._adapter = DebugAdapter.for_script(filename, *argv,
                                                port=self._port)
        return self._adapter, self._adapter.attach(**kwargs)

    def launch_module(self, module, *argv, **kwargs):
        if self._adapter is not None:
            raise RuntimeError('debugger already running')
        self._adapter = DebugAdapter.for_module(module, *argv,
                                                port=self._port)
        return self._adapter, self._adapter.attach(**kwargs)

    def detach(self):
        if self._adapter is None:
            raise RuntimeError('debugger not running')
        self._adapter.detach()

    def attach(self, **kwargs):
        if self._adapter is None:
            raise RuntimeError('debugger not running')
        self._adapter, self._adapter.attach(**kwargs)

    # internal methods

    def _close(self):
        if self._adapter is not None:
            self._adapter.close()
