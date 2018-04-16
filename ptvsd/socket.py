from __future__ import absolute_import

from collections import namedtuple
import contextlib
import errno
import socket


NOT_CONNECTED = (
    errno.ENOTCONN,
    errno.EBADF,
)


def create_server(host, port):
    """Return a local server socket listening on the given port."""
    if host is None:
        host = 'localhost'
    server = _new_sock()
    server.bind((host, port))
    server.listen(1)
    return server


def create_client():
    """Return a client socket that may be connected to a remote address."""
    return _new_sock()


def _new_sock():
    sock = socket.socket(socket.AF_INET,
                         socket.SOCK_STREAM,
                         socket.IPPROTO_TCP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    return sock


@contextlib.contextmanager
def ignored_errno(*ignored):
    """A context manager that ignores the given errnos."""
    try:
        yield
    except OSError as exc:
        if exc.errno not in ignored:
            raise


def shut_down(sock, how=socket.SHUT_RDWR, ignored=NOT_CONNECTED):
    """Shut down the given socket."""
    with ignored_errno(*ignored or ()):
        sock.shutdown(how)


def close_socket(sock):
    """Shutdown and close the socket."""
    try:
        shut_down(sock)
    except Exception:
        pass
    sock.close()


class Address(namedtuple('Address', 'host port')):
    """An IP address to use for sockets."""

    @classmethod
    def from_raw(cls, raw):
        """Return an address corresponding to the given data."""
        if isinstance(raw, cls):
            return raw
        if isinstance(raw, str):
            raise NotImplementedError
        try:
            kwargs = dict(**raw)
        except TypeError:
            return cls(*raw)
        else:
            return cls(**kwargs)

    @classmethod
    def as_server(cls, host, port):
        """Return an address to use as a server address."""
        return cls(host, port, isserver=True)

    @classmethod
    def as_client(cls, host, port):
        """Return an address to use as a server address."""
        return cls(host, port, isserver=False)

    def __new__(cls, host, port, **kwargs):
        isserver = kwargs.pop('isserver', None)
        if isserver is None:
            isserver = (host is None or host == '')
        else:
            isserver = bool(isserver)
        if host is None:
            host = 'localhost'
        self = super(Address, cls).__new__(
            cls,
            str(host),
            int(port) if port is not None else None,
            **kwargs
        )
        self._isserver = isserver
        return self

    def __init__(self, *args, **kwargs):
        if self.port is None:
            raise TypeError('missing port')
        if self.port <= 0 or self.port > 65535:
            raise ValueError('port must be positive int < 65535')

    def __repr__(self):
        orig = super(Address, self).__repr__()
        return '{}, isserver={})'.format(orig[:-1], self._isserver)

    def __eq__(self, other):
        if not super(Address, self).__eq__(other):
            return False
        try:
            other = self.from_raw(other)
        except Exception:
            return False
        return self._isserver == other._isserver

    @property
    def isserver(self):
        return self._isserver
