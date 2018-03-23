from __future__ import absolute_import

from collections import namedtuple
import errno
import socket

import ptvsd.wrapper as _ptvsd


def create_server(address):
    """Return a server socket after binding."""
    host, port = address
    return _ptvsd._create_server(port)


def create_client():
    """Return a new (unconnected) client socket."""
    return _ptvsd._create_client()


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


def close(sock):
    """Shutdown and close the socket."""
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except Exception:
        pass
    sock.close()


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
            try:
                self.server.shutdown(*args, **kwargs)
            except OSError as exc:
                if exc.errno not in (errno.ENOTCONN, errno.EBADF):
                    raise
        try:
            self.client.shutdown(*args, **kwargs)
        except OSError as exc:
            if exc.errno not in (errno.ENOTCONN, errno.EBADF):
                raise

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
