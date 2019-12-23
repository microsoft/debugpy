# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, division, print_function, unicode_literals

import socket
import sys
import threading

from ptvsd.common import log


def create_server(host, port, timeout=None):
    """Return a local server socket listening on the given port."""
    if host is None:
        host = "127.0.0.1"
    if port is None:
        port = 0

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
    if sys.platform == "win32":
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


class ClientConnection(object):
    listener = None
    """After listen() is invoked, this is the socket listening for connections.
    """

    @classmethod
    def listen(cls, host=None, port=0, timeout=None, name=None):
        """Accepts TCP connections on the specified host and port, and creates a new
        instance of this class wrapping every accepted socket.
        """

        if name is None:
            name = cls.__name__

        assert cls.listener is None
        try:
            cls.listener = create_server(host, port, timeout)
        except Exception:
            raise log.exception(
                "Error listening for incoming {0} connections on {1}:{2}:",
                name,
                host,
                port,
            )
        host, port = cls.listener.getsockname()
        log.info("Listening for incoming {0} connections on {1}:{2}...", name, host, port)

        def accept_worker():
            while True:
                try:
                    sock, (other_host, other_port) = cls.listener.accept()
                except OSError:
                    # Listener socket has been closed.
                    break

                log.info(
                    "Accepted incoming {0} connection from {1}:{2}.",
                    name,
                    other_host,
                    other_port,
                )
                cls(sock)

        thread = threading.Thread(target=accept_worker)
        thread.daemon = True
        thread.pydev_do_not_trace = True
        thread.is_pydev_daemon_thread = True
        thread.start()

        return host, port
