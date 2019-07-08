# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import ptvsd
from ptvsd.common import log, messaging, singleton, socket


class Channels(singleton.ThreadSafeSingleton):

    ide = None
    """DAP channel to the IDE over stdin/stdout.

    Created by main() as soon as the adapter process starts.

    When the IDE disconnects, the channel remains, but is closed, and will raise
    EOFError on writes.
    """

    server = None
    """DAP channel to the debug server over a socket.

    Created when handling the "attach" or "launch" request.

    When the server disconnects, the channel remains, but is closed, and will raise
    EOFError on writes.
    """

    @singleton.autolocked_method
    def connect_to_ide(self, address=None):
        assert self.ide is None

        # Import message handlers lazily to avoid circular imports.
        from ptvsd.adapter import messages

        if address is None:
            ide_stream = messaging.JsonIOStream.from_stdio("IDE")
        else:
            host, port = address
            server_sock = socket.create_server(host, port)
            try:
                log.info(
                    "ptvsd debugServer waiting for connection on {0}:{1}...",
                    host,
                    port,
                )
                sock, (ide_host, ide_port) = server_sock.accept()
            finally:
                server_sock.close()
            log.info("IDE connection accepted from {0}:{1}.", ide_host, ide_port)
            ide_stream = messaging.JsonIOStream.from_socket(sock, "IDE")

        self.ide = messaging.JsonMessageChannel(
            ide_stream, messages.IDEMessages(), ide_stream.name
        )
        self.ide.start()
        self.ide.send_event(
            "output",
            {
                "category": "telemetry",
                "output": "ptvsd.adapter",
                "data": {"version": ptvsd.__version__},
            },
        )


    @singleton.autolocked_method
    def connect_to_server(self, address):
        assert self.server is None
        raise NotImplementedError

    @singleton.autolocked_method
    def accept_connection_from_server(self, address):
        assert self.server is None
        raise NotImplementedError
