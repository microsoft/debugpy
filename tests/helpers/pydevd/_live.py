import os
import os.path
import sys
import threading

import _pydevd_bundle.pydevd_comm as pydevd_comm

from ptvsd import wrapper, debugger
from tests.helpers import protocol, socket


class Connection(object):

    @classmethod
    def connect(cls, address, _connect=None):
        if _connect is None:
            _connect, _ = socket.bind(address)
        client, server = _connect()
        return cls(client, server)

    def __init__(self, client, server):
        self._client = client
        self._server = server
        self._fakesock = None

    def start(self):
        if self._fakesock is not None:
            return self._fakesock
        self._fakesock = wrapper._start(self._client, self._server,
                                        killonclose=False,
                                        addhandlers=False)
        return self._fakesock


class LivePyDevd(protocol.Daemon):

    @classmethod
    def parse_source(cls, source):
        kind, sep, name = source.partition(':')
        if kind == 'file':
            return name, None, False
        elif kind == 'module':
            parts = (name + '.py').split('.')
            filename = os.path.join(*parts)
            return filename, name, False
        else:
            # TODO: Write source code to temp module?
            raise NotImplementedError

    def __init__(self, source):
        filename, module, owned = self.parse_source(source)
        self._filename = filename
        self._owned = owned
        self._conn = None

        def bind(address):
            _connect, remote = socket.bind(address)
            waiter = threading.Lock()
            waiter.acquire()

            def new_pydevd_sock(*args):
                if self._conn is not None:
                    raise RuntimeError('already connected')
                self._conn = Connection.connect(address, _connect=_connect)
                sock = self._conn.start()
                waiter.release()
                return sock

            def connect():
                pydevd_comm.start_server = new_pydevd_sock
                pydevd_comm.start_client = new_pydevd_sock
                # Force a fresh pydevd.
                sys.modules.pop('pydevd', None)
                if module is None:
                    debugger._run_file(address, filename)
                else:
                    debugger._run_module(address, module)
                waiter.acquire(timeout=1)
                waiter.release()
            return connect, remote
        super(LivePyDevd, self).__init__(bind)

    def _close(self):
        super(LivePyDevd, self)._close()
        # TODO: Close pydevd somehow?

        if self._owned:
            os.unlink(self._filename)
