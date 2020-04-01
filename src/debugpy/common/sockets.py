# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, division, print_function, unicode_literals

import socket
import sys
import threading

from debugpy.common import log


def create_server(host, port=0, backlog=socket.SOMAXCONN, timeout=None):
    """Return a local server socket listening on the given port."""

    assert backlog > 0
    if host is None:
        host = "127.0.0.1"
    if port is None:
        port = 0

    try:
        server = _new_sock()
        server.bind((host, port))
        if timeout is not None:
            server.settimeout(timeout)
        server.listen(backlog)
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


def serve(name, handler, host, port=0, backlog=socket.SOMAXCONN, timeout=None):
    """Accepts TCP connections on the specified host and port, and invokes the
    provided handler function for every new connection.

    Returns the created server socket.
    """

    assert backlog > 0

    try:
        listener = create_server(host, port, backlog, timeout)
    except Exception:
        log.reraise_exception(
            "Error listening for incoming {0} connections on {1}:{2}:", name, host, port
        )
    host, port = listener.getsockname()
    log.info("Listening for incoming {0} connections on {1}:{2}...", name, host, port)

    def accept_worker():
        while True:
            try:
                sock, (other_host, other_port) = listener.accept()
            except (OSError, socket.error):
                # Listener socket has been closed.
                break

            log.info(
                "Accepted incoming {0} connection from {1}:{2}.",
                name,
                other_host,
                other_port,
            )
            handler(sock)

    thread = threading.Thread(target=accept_worker)
    thread.daemon = True
    thread.pydev_do_not_trace = True
    thread.is_pydev_daemon_thread = True
    thread.start()

    return listener
