# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, division, print_function, unicode_literals

__all__ = []

import os

# Force absolute path on Python 2.
__file__ = os.path.abspath(__file__)


channel = None
"""DAP message channel to the adapter."""


def connect(launcher_port):
    from ptvsd.common import messaging, sockets
    from ptvsd.launcher import handlers

    global channel
    assert channel is None

    sock = sockets.create_client()
    sock.connect(("127.0.0.1", launcher_port))

    stream = messaging.JsonIOStream.from_socket(sock, "Adapter")
    channel = messaging.JsonMessageChannel(stream, handlers=handlers)
    channel.start()
