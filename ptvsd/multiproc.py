# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

import atexit
import itertools
import os
import random
import socket

try:
    import queue
except ImportError:
    import Queue as queue

import ptvsd
from .socket import create_server, create_client
from .messaging import JsonIOStream, JsonMessageChannel
from ._util import new_hidden_thread, debug

import pydevd
from _pydev_bundle import pydev_monkey


# Defaults to the intersection of default ephemeral port ranges for various common systems.
subprocess_port_range = (49152, 61000)

listener_port = None

subprocess_queue = queue.Queue()


def enable():
    global listener_port, _server
    _server = create_server('localhost', 0)
    atexit.register(disable)
    _, listener_port = _server.getsockname()

    listener_thread = new_hidden_thread('SubprocessListener', _listener)
    listener_thread.start()


def disable():
    try:
        _server.shutdown(socket.SHUT_RDWR)
    except Exception:
        pass

def _listener():
    counter = itertools.count(1)
    while listener_port:
        (sock, _) = _server.accept()
        stream = JsonIOStream.from_socket(sock)
        _handle_subprocess(next(counter), stream)


def _handle_subprocess(n, stream):
    class Handlers(object):
        def ptvsd_subprocess_event(self, channel, body):
            debug('ptvsd_subprocess: %r' % body)
            subprocess_queue.put(body)
            channel.close()

    name = 'SubprocessListener-%d' % n
    channel = JsonMessageChannel(stream, Handlers(), name)
    channel.start()


def init_subprocess(parent_port, first_port, last_port, pydevd_setup):
    # Called from the code injected into subprocess, before it starts
    # running user code. See pydevd_hooks.get_python_c_args.

    global listener_port, subprocess_port_range
    listener_port = parent_port
    subprocess_port_range = (first_port, last_port)

    pydevd.SetupHolder.setup = pydevd_setup
    pydev_monkey.patch_new_process_functions()

    ports = list(range(first_port, last_port))
    random.shuffle(ports)
    for port in ports:
        try:
            ptvsd.enable_attach(('localhost', port))
        except IOError:
            pass
        else:
            debug('Child process %d listening on port %d' % (os.getpid(), port))
            break
    else:
        raise Exception('Could not find a free port in range {first_port}-{last_port}')

    enable()

    debug('Child process %d notifying parent process at port %d' % (os.getpid(), parent_port))
    conn = create_client()
    conn.connect(('localhost', parent_port))
    stream = JsonIOStream.from_socket(conn)
    channel = JsonMessageChannel(stream)
    channel.send_event('ptvsd_subprocess', {
        'processId': os.getpid(),
        'port': port,
    })

    debug('Child process %d notified parent process; waiting for connection.' % os.getpid())
    ptvsd.wait_for_attach()


