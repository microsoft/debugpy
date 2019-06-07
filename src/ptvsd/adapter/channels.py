# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

from ptvsd.common import messaging, singleton


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
    def connect_to_ide(self):
        assert self.ide is None

        # Import message handlers lazily to avoid circular imports.
        from ptvsd.adapter import messages

        ide_channel = messaging.JsonIOStream.from_stdio("IDE")
        self.ide = messaging.JsonMessageChannel(
            ide_channel, messages.IDEMessages(), ide_channel.name
        )
        self.ide.start()

    @singleton.autolocked_method
    def connect_to_server(self, address):
        assert self.server is None
        raise NotImplementedError

    @singleton.autolocked_method
    def accept_connection_from_server(self, address):
        assert self.server is None
        raise NotImplementedError
