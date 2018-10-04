# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

"""Imported from test code that runs under ptvsd, and allows that code
to communcate back to the test. Works in conjunction with debug_session
fixture and its backchannel method."""

import os
import socket

from ptvsd.messaging import JsonIOStream

port = int(os.getenv('PTVSD_BACKCHANNEL_PORT'))
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect(('localhost', port))
stream = JsonIOStream.from_socket(sock)


def read_json():
    return stream.read_json()


def write_json(value):
    stream.write_json(value)
