# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, division, print_function, unicode_literals

"""Imported from test code that runs under debugpy, and allows that code
to communcate back to the test. Works in conjunction with debug_session
fixture and its backchannel method."""

__all__ = ["port", "receive", "send"]

import atexit
import os
import socket

import debuggee
from debugpy.common import fmt, log, messaging


def send(value):
    _stream.write_json(value)


def receive():
    return _stream.read_json()


def close():
    global _socket, _stream
    if _socket is None:
        return

    log.info("Shutting down {0}...", name)
    try:
        _socket.shutdown(socket.SHUT_RDWR)
    except Exception:
        pass
    finally:
        _socket = None
        try:
            _stream.close()
        except Exception:
            pass
        finally:
            _stream = None


class _stream:
    def _error(*_):
        raise AssertionError("Backchannel is not set up for this process")

    read_json = write_json = _error
    close = lambda: None


name = fmt("backchannel-{0}", debuggee.session_id)
port = os.environ.pop("DEBUGPY_TEST_BACKCHANNEL_PORT", None)
if port is not None:
    port = int(port)
    log.info("Connecting {0} to port {1}...", name, port)

    _socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        _socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        _socket.connect(("localhost", port))
    except Exception:
        _socket.close()
        raise
    else:
        _stream = messaging.JsonIOStream.from_socket(  # noqa
            _socket, name="backchannel"
        )
        atexit.register(close)
