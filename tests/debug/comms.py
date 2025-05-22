# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

"""Various means of communication with the debuggee."""

import threading
import socket

from debugpy.common import log, messaging, sockets


class BackChannel(object):
    TIMEOUT = 60

    def __init__(self, session):
        self.session = session
        self.port = None
        self._established = threading.Event()
        self._socket = None
        self._server_socket = None

    def __str__(self):
        return f"BackChannel[{self.session.id}]"

    def listen(self):
        self._server_socket = sockets.create_server("127.0.0.1", 0, self.TIMEOUT)
        _, self.port = sockets.get_address(self._server_socket)
        self._server_socket.listen(0)

        def accept_worker():
            log.info(
                "Listening for incoming connection from {0} on port {1}...",
                self,
                self.port,
            )

            server_socket = self._server_socket
            if server_socket is None:
                return  # concurrent close()

            try:
                sock, _ = server_socket.accept()
            except socket.timeout:
                if self._server_socket is None:
                    return
                else:
                    log.reraise_exception("Timed out waiting for {0} to connect", self)
            except Exception:
                if self._server_socket is None:
                    return
                else:
                    log.reraise_exception("Error accepting connection for {0}:", self)

            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            log.info("Incoming connection from {0} accepted.", self)

            self._socket = sock
            self._setup_stream()

        accept_thread = threading.Thread(target=accept_worker, name=f"{self} listener")
        accept_thread.daemon = True
        accept_thread.start()

    def _setup_stream(self):
        self._stream = messaging.JsonIOStream.from_socket(self._socket, name=str(self))
        self._established.set()

    def receive(self):
        self._established.wait()
        return self._stream.read_json()

    def send(self, value):
        self.session.timeline.unfreeze()
        self._established.wait()
        t = self.session.timeline.mark(("sending", value))
        self._stream.write_json(value)
        return t

    def close(self):
        sock = self._socket
        if sock:
            self._socket = None
            log.debug("Closing {0} client socket...", self)
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                sock.close()
            except Exception:
                pass

        server_socket = self._server_socket
        if server_socket:
            self._server_socket = None
            log.debug("Closing {0} server socket...", self)
            try:
                server_socket.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                server_socket.close()
            except Exception:
                pass


class ScratchPad(object):
    def __init__(self, session):
        self.session = session

    def __getitem__(self, key):
        raise NotImplementedError

    def __setitem__(self, key, value):
        """Sets debuggee.scratchpad[key] = value inside the debugged process."""
        log.info("{0} debuggee.scratchpad[{1!r}] = {2!r}", self.session, key, value)
        expr = f"sys.modules['debuggee'].scratchpad[{key!r}] = {value!r}"
        self.session.request("evaluate", {"context": "repl", "expression": expr})
