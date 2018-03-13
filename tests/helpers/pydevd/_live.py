import os
import os.path
import sys
import threading

import _pydevd_bundle.pydevd_comm as pydevd_comm

from ptvsd import wrapper, debugger
from tests.helpers import protocol, socket


class Binder(object):

    def __init__(self, filename, module):
        self.filename = filename
        self.module = module

        self.address = None
        self._waiter = None
        self._connect = None

        self._thread = None
        self.client = None
        self.server = None
        self.fakesock = None
        self.proc = None

    def bind(self, address):
        if self._connect is not None:
            raise RuntimeError('already bound')
        self.address = address
        self._connect, remote = socket.bind(address)
        self._waiter = threading.Lock()
        self._waiter.acquire()

        def connect():
            self._thread = threading.Thread(target=self.run_pydevd)
            self._thread.start()
            if self._waiter.acquire(timeout=1):
                self._waiter.release()
            else:
                raise RuntimeError('timed out')
            return socket.Connection(self.client, self.server)
            #return socket.Connection(self.fakesock, self.server)
        return connect, remote

    def new_pydevd_sock(self, *args):
        if self.client is not None:
            raise RuntimeError('already connected')
        self.client, self.server = self._connect()
        self.fakesock = wrapper._start(self.client, self.server,
                                       killonclose=False,
                                       addhandlers=False)
        self.proc = self.fakesock._vscprocessor
        self._waiter.release()
        return self.fakesock

    def run_pydevd(self):
        pydevd_comm.start_server = self.new_pydevd_sock
        pydevd_comm.start_client = self.new_pydevd_sock
        # Force a fresh pydevd.
        sys.modules.pop('pydevd', None)
        try:
            if self.module is None:
                debugger._run_file(self.address, self.filename)
            else:
                debugger._run_module(self.address, self.module)
        except SystemExit as exc:
            wrapper.ptvsd_sys_exit_code = int(exc.code)
            raise
        wrapper.ptvsd_sys_exit_code = 0
        self.proc.close()

    def wait_until_done(self):
        if self._thread is None:
            return
        self._thread.join()


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
        self.binder = Binder(filename, module)

        super(LivePyDevd, self).__init__(self.binder.bind)

    def _close(self):
        super(LivePyDevd, self)._close()
        # TODO: Close pydevd somehow?

        if self._owned:
            os.unlink(self._filename)
