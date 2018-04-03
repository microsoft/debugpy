import atexit
import os
import platform
import signal
import socket
import sys

from _pydevd_bundle import pydevd_comm

from ptvsd import wrapper


def _wait_on_exit():
    if sys.__stdout__ is not None:
        try:
            import msvcrt
        except ImportError:
            sys.__stdout__.write('Press Enter to continue . . . ')
            sys.__stdout__.flush()
            sys.__stdin__.read(1)
        else:
            sys.__stdout__.write('Press any key to continue . . . ')
            sys.__stdout__.flush()
            msvcrt.getch()


class Daemon(object):

    exitcode = 0

    def __init__(self, wait_on_exit=_wait_on_exit,
                 addhandlers=True, killonclose=True):
        self.wait_on_exit = wait_on_exit
        self.addhandlers = addhandlers
        self.killonclose = killonclose

        self._closed = False

        self._pydevd = None
        self._server = None
        self._client = None
        self._adapter = None

    @property
    def pydevd(self):
        return self._pydevd

    @property
    def server(self):
        return self._server

    @property
    def client(self):
        return self._client

    @property
    def adapter(self):
        return self._adapter

    def start(self, server=None):
        if self._closed:
            raise RuntimeError('closed')
        if self._pydevd is not None:
            raise RuntimeError('already started')
        self._pydevd = wrapper.PydevdSocket(
            self._handle_pydevd_message,
            self._handle_pydevd_close,
            self._getpeername,
            self._getsockname,
        )
        self._server = server
        return self._pydevd

    def set_connection(self, client):
        if self._closed:
            raise RuntimeError('closed')
        if self._pydevd is None:
            raise RuntimeError('not started yet')
        if self._client is not None:
            raise RuntimeError('connection already set')
        self._client = client

        self._adapter = wrapper.VSCodeMessageProcessor(
            client,
            self._pydevd,
            self._handle_vsc_disconnect,
            self._handle_vsc_close,
        )
        name = 'ptvsd.Client' if self._server is None else 'ptvsd.Server'
        self._adapter.start(name)
        if self.addhandlers:
            self._add_atexit_handler()
            self._set_signal_handlers()
        return self._adapter

    def close(self):
        if self._closed:
            raise RuntimeError('already closed')
        self._closed = True

        if self._adapter is not None:
            normal, abnormal = self._adapter._wait_options()
            if (normal and not self.exitcode) or (abnormal and self.exitcode):
                self.wait_on_exit_func()

        if self._pydevd is not None:
            self._pydevd.shutdown(socket.SHUT_RDWR)
            self._pydevd.close()
        if self._client is not None:
            self._release_connection()

    # internal methods

    def _add_atexit_handler(self):
        def handler():
            if not self._closed:
                self.close()
            if self._adapter.server_thread.is_alive():
                self._adapter.server_thread.join(
                    wrapper.WAIT_FOR_THREAD_FINISH_TIMEOUT)
        atexit.register(handler)

    def _set_signal_handlers(self):
        if platform.system() == 'Windows':
            return None

        def handler(signum, frame):
            if not self._closed:
                self.close()
            sys.exit(0)
        signal.signal(signal.SIGHUP, handler)

    def _release_connection(self):
        if self._adapter is not None:
            # TODO: This is not correct in the "attach" case.
            self._adapter.handle_pydevd_stopped(self.exitcode)
            self._adapter.close()
        self._client.shutdown(socket.SHUT_RDWR)
        self._client.close()

    # internal methods for PyDevdSocket().

    def _handle_pydevd_message(self, cmdid, seq, text):
        if self._adapter is not None:
            self._adapter.on_pydevd_event(cmdid, seq, text)

    def _handle_pydevd_close(self):
        if self._closed:
            return
        self.close()

    def _getpeername(self):
        if self._client is None:
            raise NotImplementedError
        return self._client.getpeername()

    def _getsockname(self):
        if self._client is None:
            raise NotImplementedError
        return self._client.getsockname()

    # internal methods for VSCodeMessageProcessor

    def _handle_vsc_disconnect(self, kill=False):
        if not self._closed:
            self.close()
        if kill and self.killonclose:
            os.kill(os.getpid(), signal.SIGTERM)

    def _handle_vsc_close(self):
        if self._closed:
            return
        self.close()


########################
# pydevd hooks

def _create_server(port):
    server = _new_sock()
    server.bind(('127.0.0.1', port))
    server.listen(1)
    return server


def _create_client():
    return _new_sock()


def _new_sock():
    sock = socket.socket(socket.AF_INET,
                         socket.SOCK_STREAM,
                         socket.IPPROTO_TCP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    return sock


def start_server(daemon, port):
    """Return a socket to a (new) local pydevd-handling daemon.

    The daemon supports the pydevd client wire protocol, sending
    requests and handling responses (and events).

    This is a replacement for _pydevd_bundle.pydevd_comm.start_server.
    """
    server = _create_server(port)
    client, _ = server.accept()

    pydevd = daemon.start(server)
    daemon.set_connection(client)
    return pydevd


def start_client(daemon, host, port):
    """Return a socket to an existing "remote" pydevd-handling daemon.

    The daemon supports the pydevd client wire protocol, sending
    requests and handling responses (and events).

    This is a replacement for _pydevd_bundle.pydevd_comm.start_client.
    """
    client = _create_client()
    client.connect((host, port))

    pydevd = daemon.start()
    daemon.set_connection(client)
    return pydevd


def install(pydevd, start_server=start_server, start_client=start_client):
    """Configure pydevd to use our wrapper.

    This is a bit of a hack to allow us to run our VSC debug adapter
    in the same process as pydevd.  Note that, as with most hacks,
    this is somewhat fragile (since the monkeypatching sites may
    change).
    """
    daemon = Daemon()

    # These are the functions pydevd invokes to get a socket to the client.
    pydevd_comm.start_server = (lambda p: start_server(daemon, p))
    pydevd_comm.start_client = (lambda h, p: start_client(daemon, h, p))

    # Ensure that pydevd is using our functions.
    pydevd.start_server = start_server
    pydevd.start_client = start_client
    __main__ = sys.modules['__main__']
    if __main__ is not pydevd and __main__.__file__ == pydevd.__file__:
        __main__.start_server = start_server
        __main__.start_client = start_client
    return daemon
