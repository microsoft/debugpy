# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, division, print_function, unicode_literals

"""Various means of communication with the debuggee."""

import threading
import socket

from ptvsd.common import fmt, log, messaging, sockets
from tests.timeline import Request, Response


class BackChannel(object):
    TIMEOUT = 20

    def __init__(self, session):
        self.session = session
        self.port = None
        self._established = threading.Event()
        self._socket = None
        self._server_socket = None

    def __str__(self):
        return fmt("{0}.backchannel", self.session.debuggee_id)

    def listen(self):
        self._server_socket = sockets.create_server("127.0.0.1", 0, self.TIMEOUT)
        _, self.port = self._server_socket.getsockname()
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
                raise log.exception("Timed out waiting for {0} to connect", self)

            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            log.info("Incoming connection from {0} accepted.", self)

            self._socket = sock
            self._setup_stream()

        accept_thread = threading.Thread(
            target=accept_worker, name=fmt("{0} listener", self)
        )
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
            log.debug("Closing {0} socket of {1}...", self, self.session)
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass

        server_socket = self._server_socket
        if server_socket:
            self._server_socket = None
            log.debug("Closing {0} server socket of {1}...", self, self.session)
            try:
                server_socket.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass


class ScratchPad(object):
    def __init__(self, session):
        self.session = session

    def __getitem__(self, key):
        raise NotImplementedError

    def __setitem__(self, key, value):
        """Sets debug_me.scratchpad[key] = value inside the debugged process.
        """

        stackTrace_responses = self.session.all_occurrences_of(
            Response(Request("stackTrace"))
        )
        assert (
            stackTrace_responses
        ), 'scratchpad requires at least one "stackTrace" request in the timeline.'
        stack_trace = stackTrace_responses[-1].body
        frame_id = stack_trace["stackFrames"][0]["id"]

        log.info("{0} debug_me.scratchpad[{1!r}] = {2!r}", self.session, key, value)
        expr = fmt("__import__('debug_me').scratchpad[{0!r}] = {1!r}", key, value)
        self.session.request(
            "evaluate", {"frameId": frame_id, "context": "repl", "expression": expr}
        )
