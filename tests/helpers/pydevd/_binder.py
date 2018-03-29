from collections import namedtuple
import threading
import time

from ptvsd import wrapper
from tests.helpers import socket


class PTVSD(namedtuple('PTVSD', 'client server proc fakesock')):
    """A wrapper around a running "instance" of PTVSD.

    "client" and "server" are the two ends of socket that PTVSD uses
    to communicate with the editor (e.g. VSC) via the VSC debug adapter
    protocol.  "server" will be None for a remote address.
    "proc" is the wrapper around the VSC message handler.
    "fakesock" is the socket-like object that PTVSD uses to communicate
    with the debugger (e.g. PyDevd) via the PyDevd wire protocol.
    """

    @classmethod
    def from_connect_func(cls, connect):
        """Return a new instance using the socket returned by connect()."""
        client, server = connect()
        fakesock = wrapper._start(
            client,
            server,
            killonclose=False,
            addhandlers=False,
        )
        proc = fakesock._vscprocessor
        proc._exit_on_unknown_command = False
        return cls(client, server, proc, fakesock)

    def close(self):
        """Stop PTVSD and clean up.

        This will trigger the VSC protocol end-of-debugging message flow
        (e.g. "exited" and "terminated" events).  As part of that flow
        this function may block while waiting for specific messages from
        the editor (e.g. a "disconnect" request).  PTVSD also closes all
        of its background threads and closes any sockets it controls.
        """
        self.proc.close()


class BinderBase(object):
    """Base class for one-off socket binders (for protocol daemons).

    A "binder" facilitates separating the socket-binding behavior from
    the socket-connecting behavior.  This matters because for server
    sockets the connecting part is a blocking operation.

    The bind method may be passed to protocol.Daemon() as the "bind"
    argument.

    Note that a binder starts up ptvsd using the connected socket and
    runs the debugger in the background.
    """

    def __init__(self, address=None, ptvsd=None):
        if address is not None or ptvsd is not None:
            raise NotImplementedError

        # Set when bind() called:
        self.address = None
        self._connect = None
        self._waiter = None

        # Set when ptvsd started:
        self._thread = None
        self.ptvsd = None

    def __repr__(self):
        return '{}(address={!r}, ptvsd={!r})'.format(
            type(self).__name__,
            self.address,
            self.ptvsd,
        )

    def bind(self, address):
        """Return (connect func, remote addr) after binding a socket.

        A new client or server socket is immediately bound, depending on
        the address.  Then the connect func is generated for that
        socket.  The func takes no args and returns a client socket
        connected to the original address.  In the case of a remote
        address, that socket may be the one that was originally bound.

        When the connect func is called, PTVSD is started up using the
        socket.  Then some debugging operation (e.g. running a script
        through pydevd) is started in a background thread.
        """
        if self._connect is not None:
            raise RuntimeError('already bound')
        self.address = address
        self._connect, remote = socket.bind(address)
        self._waiter = threading.Lock()
        self._waiter.acquire()

        def connect():
            if self._thread is not None:
                raise RuntimeError('already connected')
            self._thread = threading.Thread(target=self._run)
            self._thread.start()
            # Wait for ptvsd to start up.
            if self._waiter.acquire(timeout=1):
                self._waiter.release()
            else:
                raise RuntimeError('timed out')
            return self._wrap_sock()
        return connect, remote

    def wait_until_done(self):
        """Wait for the started debugger operation to finish."""
        if self._thread is None:
            return
        self._thread.join()

    ####################
    # for subclassing

    def _run_debugger(self):
        # Subclasses import this.  The method must directly or
        # indirectly call self._start_ptvsd().
        raise NotImplementedError

    def _wrap_sock(self):
        return socket.Connection(self.ptvsd.client, self.ptvsd.server)
        #return socket.Connection(self.ptvsd.fakesock, self.ptvsd.server)

    ####################
    # internal methods

    def _start_ptvsd(self):
        if self.ptvsd is not None:
            raise RuntimeError('already connected')
        self.ptvsd = PTVSD.from_connect_func(self._connect)
        self._waiter.release()

    def _run(self):
        try:
            self._run_debugger()
        except SystemExit as exc:
            wrapper.ptvsd_sys_exit_code = int(exc.code)
            raise
        wrapper.ptvsd_sys_exit_code = 0
        self.ptvsd.proc.close()


class Binder(BinderBase):
    """A "binder" that defers the debugging operation to an external func.

    That function takes two arguments, "external" and "internal", and
    returns nothing.  "external" is a socket that an editor (or fake)
    may use to communicate with PTVSD over the VSC debug adapter
    protocol.  "internal does the same for a debugger and the PyDevd
    wire protocol.  The function should exit once debugging has
    finished.
    """

    def __init__(self, do_debugging=None):
        if do_debugging is None:
            def do_debugging(external, internal):
                time.sleep(5)
        super(Binder, self).__init__()
        self._do_debugging = do_debugging

    def _run_debugger(self):
        self._start_ptvsd()
        external = self.ptvsd.server
        internal = self.ptvsd.fakesock
        self._do_debugging(external, internal)
