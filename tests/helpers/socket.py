from __future__ import absolute_import

import socket


def connect(host, port):
    """Return (client, server) after connecting.

    If host is None then it's a server, so it will wait for a connection
    on localhost.  Otherwise it will connect to the remote host.
    """
    sock = socket.socket(
        socket.AF_INET,
        socket.SOCK_STREAM,
        socket.IPPROTO_TCP,
    )
    sock.setsockopt(
        socket.SOL_SOCKET,
        socket.SO_REUSEADDR,
        1,
    )
    if host is None:
        addr = ('127.0.0.1', port)
        server = sock
        server.bind(addr)
        server.listen(1)
        sock, _ = server.accept()
    else:
        addr = (host, port)
        sock.connect(addr)
        server = None
    return sock, server


def close(sock):
    """Shutdown and close the socket."""
    sock.shutdown(socket.SHUT_RDWR)
    sock.close()
