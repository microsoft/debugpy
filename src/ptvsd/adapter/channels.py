# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import os
import sys

from ptvsd.common import log, messaging, singleton, socket


class Channels(singleton.ThreadSafeSingleton):
    _ide = None

    @singleton.autolocked_method
    def ide(self):
        """DAP channel to the IDE over stdin/stdout.

        Created by main() as soon as the adapter process starts.

        If the IDE has disconnected, this method still returns the closed channel.
        """
        return self._ide

    _server = None

    @singleton.autolocked_method
    def server(self):
        """DAP channel to the debug server over a socket.

        Created when handling the "attach" or "launch" request.

        When the server disconnects, the channel remains, but is closed, and will raise
        NoMoreMessages on writes.
        """
        return self._server

    @singleton.autolocked_method
    def connect_to_ide(self, address=None):
        """Creates a DAP message channel to the IDE, and returns that channel.

        If address is not None, the channel is established by connecting to the TCP
        socket listening on that address. Otherwise, the channel is established over
        stdio.

        Caller is responsible for calling start() on the returned channel.
        """

        assert self._ide is None

        # Import message handlers lazily to avoid circular imports.
        from ptvsd.adapter import messages

        if address is None:
            ide_stream = messaging.JsonIOStream.from_stdio("IDE")
            # Make sure that nothing else tries to interfere with the stdio streams
            # that are going to be used for DAP communication from now on.
            sys.stdout = sys.stderr
            sys.stdin = open(os.devnull, "r")
        else:
            host, port = address
            listener = socket.create_server(host, port)
            try:
                log.info(
                    "Adapter waiting for connection from IDE on {0}:{1}...", host, port
                )
                sock, (ide_host, ide_port) = listener.accept()
            finally:
                listener.close()
            log.info("IDE connection accepted from {0}:{1}.", ide_host, ide_port)
            ide_stream = messaging.JsonIOStream.from_socket(sock, "IDE")

        self._ide = messaging.JsonMessageChannel(
            ide_stream, messages.IDEMessages(), ide_stream.name
        )
        return self._ide

    @singleton.autolocked_method
    def connect_to_server(self, address):
        """Creates a DAP message channel to the server, and returns that channel.

        The channel is established by connecting to the TCP socket listening on the
        specified address

        Caller is responsible for calling start() on the returned channel.
        """

        assert self._server is None

        # Import message handlers lazily to avoid circular imports.
        from ptvsd.adapter import messages

        host, port = address
        sock = socket.create_client()
        sock.connect(address)

        server_stream = messaging.JsonIOStream.from_socket(sock, "server")

        self._server = messaging.JsonMessageChannel(
            server_stream, messages.ServerMessages(), server_stream.name
        )
        return self._server

    @singleton.autolocked_method
    def accept_connection_from_server(self, address, before_accept=(lambda _: None)):
        """Creates a DAP message channel to the server, and returns that channel.

        The channel is established by listening on the specified address until there
        is an incoming TCP connection. Only one incoming connection is accepted.

        before_accept((host, port)) is invoked after the listener socket has been
        set up, but before the thread blocks waiting for incoming connection. This
        provides access to the actual port number if port=0.

        Caller is responsible for calling start() on the returned channel.
        """

        assert self._server is None

        # Import message handlers lazily to avoid circular imports.
        from ptvsd.adapter import messages

        host, port = address
        listener = socket.create_server(host, port)
        host, port = listener.getsockname()
        log.info(
            "Adapter waiting for connection from debug server on {0}:{1}...", host, port
        )
        before_accept((host, port))

        try:
            sock, (server_host, server_port) = listener.accept()
        finally:
            listener.close()
        log.info(
            "Debug server connection accepted from {0}:{1}.", server_host, server_port
        )
        server_stream = messaging.JsonIOStream.from_socket(sock, "server")

        self._server = server = messaging.JsonMessageChannel(
            server_stream, messages.ServerMessages(), server_stream.name
        )
        return server

    @singleton.autolocked_method
    def close_server(self):
        assert self._server is not None
        try:
            self._server.close()
        except Exception:
            log.exception("Error while closing server channel:")
        self._server = None
