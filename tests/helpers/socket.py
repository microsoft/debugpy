from __future__ import absolute_import

from collections import namedtuple
import contextlib

import ptvsd.socket as _ptvsd


convert_eof = _ptvsd.convert_eof


# TODO: Add timeouts to the functions.

def create_server(address):
    """Return a server socket after binding."""
    return _ptvsd.create_server(*address)


def create_client():
    """Return a new (unconnected) client socket."""
    return _ptvsd.create_client()


def connect(sock, address):
    """Return a client socket after connecting.

    If address is None then it's a server, so it will wait for a
    connection.  Otherwise it will connect to the remote host.
    """
    return _connect(sock, address)


def bind(address):
    """Return (connect, remote addr) for the given address.

    "connect" is a function with no args that returns (client, server),
    which are sockets.  If the host is None then a server socket will
    be created bound to localhost, and that server socket will be
    returned from connect().  Otherwise a client socket is connected to
    the remote address and None is returned from connect() for the
    server.
    """
    host, _ = address
    if host is None:
        sock = create_server(address)
        server = sock
        connect_to = None
        remote = sock.getsockname()
    else:
        sock = create_client()
        server = None
        connect_to = address
        remote = address

    def connect():
        client = _connect(sock, connect_to)
        return client, server
    return connect, remote


def recv_as_read(sock):
    """Return a wrapper ardoung sock.read that arises EOFError when closed."""
    def read(numbytes, _recv=sock.recv):
        with convert_eof():
            return _recv(numbytes)
    return read


def send_as_write(sock):
    """Return a wrapper ardoung sock.send that arises EOFError when closed."""
    def write(data, _send=sock.send):
        with convert_eof():
            return _send(data)
    return write


@contextlib.contextmanager
def timeout(sock, timeout):
    """A context manager that sets a timeout on blocking socket ops."""
    orig = sock.gettimeout()
    sock.settimeout(timeout)
    try:
        yield
    finally:
        sock.settimeout(orig)


def close(sock):
    """Shutdown and close the socket."""
    _ptvsd.close_socket(sock)


class Connection(namedtuple('Connection', 'client server')):
    """A wrapper around a client socket.

    If a server socket is provided then it will be closed when the
    client is closed.
    """

    def __new__(cls, client, server=None):
        self = super(Connection, cls).__new__(
            cls,
            client,
            server,
        )
        return self

    def send(self, *args, **kwargs):
        return self.client.send(*args, **kwargs)

    def recv(self, *args, **kwargs):
        return self.client.recv(*args, **kwargs)

    def makefile(self, *args, **kwargs):
        return self.client.makefile(*args, **kwargs)

    def shutdown(self, *args, **kwargs):
        if self.server is not None:
            _ptvsd.shut_down(self.server, *args, **kwargs)
        _ptvsd.shut_down(self.client, *args, **kwargs)

    def close(self):
        if self.server is not None:
            self.server.close()
        self.client.close()


########################
# internal functions

def _connect(sock, address):
    if address is None:
        client, _ = sock.accept()
    else:
        sock.connect(address)
        client = sock
    return client
