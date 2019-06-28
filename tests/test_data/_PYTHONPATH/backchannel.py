# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

"""Imported from test code that runs under ptvsd, and allows that code
to communcate back to the test. Works in conjunction with debug_session
fixture and its backchannel method."""

__all__ = ["port", "receive", "send"]

import atexit
import os
import socket
import sys

assert "debug_me" in sys.modules
import debug_me

from ptvsd.common import fmt, messaging


port = int(os.getenv('PTVSD_BACKCHANNEL_PORT', 0))
if port:
    print(fmt('Connecting backchannel-{0} to port {1}...', debug_me.session_id, port))

    _socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    _socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    _socket.connect(('localhost', port))
    _stream = messaging.JsonIOStream.from_socket(_socket, name='backchannel')

    receive = _stream.read_json
    send = _stream.write_json

    @atexit.register
    def _atexit_handler():
        print(fmt('Shutting down backchannel-{0}...', debug_me.session_id))
        try:
            _socket.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
