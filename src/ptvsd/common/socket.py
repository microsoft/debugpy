# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import platform
import socket


def create_server(host, port, timeout=None):
    """Return a local server socket listening on the given port."""
    if host is None:
        host = 'localhost'
    try:
        server = _new_sock()
        server.bind((host, port))
        if timeout is not None:
            server.settimeout(timeout)
        server.listen(1)
    except Exception:
        server.close()
        raise
    return server


def create_client():
    """Return a client socket that may be connected to a remote address."""
    return _new_sock()


def _new_sock():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP)
    if platform.system() == 'Windows':
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    else:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    return sock


def shut_down(sock, how=socket.SHUT_RDWR):
    """Shut down the given socket."""
    sock.shutdown(how)


def close_socket(sock):
    """Shutdown and close the socket."""
    try:
        shut_down(sock)
    except Exception:
        pass
    sock.close()
