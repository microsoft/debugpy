# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

import atexit
import itertools
import os
import random
import re
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

# The initial 'launch' or 'attach' request that started the first process
# in the current process tree.
initial_request = None

# Process ID of the first process in the current process tree.
initial_pid = os.getpid()


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


def init_subprocess(initial_pid, initial_request, parent_pid, parent_port, first_port, last_port, pydevd_setup):
    # Called from the code injected into subprocess, before it starts
    # running user code. See pydevd_hooks.get_python_c_args.

    from ptvsd import multiproc
    multiproc.listener_port = parent_port
    multiproc.subprocess_port_range = (first_port, last_port)
    multiproc.initial_pid = initial_pid
    multiproc.initial_request = initial_request

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
        'initialProcessId': initial_pid,
        'initialRequest': initial_request,
        'parentProcessId': parent_pid,
        'processId': os.getpid(),
        'port': port,
    })

    debug('Child process %d notified parent process; waiting for connection.' % os.getpid())
    ptvsd.wait_for_attach()


def patch_args(args):
    """
    Patches a command line invoking Python such that it has the same meaning, but
    the process runs under ptvsd. In general, this means that given something like:

        python -R -Q warn -m app

    the result should be:

        python -R -Q warn -m ptvsd --host localhost --port 0 --multiprocess --wait -m app

    Note that the first -m above is interpreted by Python, and the second by ptvsd.
    """

    args = list(args)
    print(args)

    # First, let's find the target of the invocation. This is one of:
    #
    #   filename.py
    #   -m module_name
    #   -c "code"
    #   -
    #
    # This needs to take into account other switches that have values:
    #
    #   -Q -W -X --check-hash-based-pycs
    #
    # because in something like "-X -c", -c is a value, not a switch.
    expect_value = False
    for i, arg in enumerate(args):
        # Skip Python binary.
        if i == 0:
            continue

        if arg == '-':
            # We do not support debugging while reading from stdin, so just let this
            # process run without debugging.
            return args

        if expect_value:
            expect_value = False
            continue

        if not arg.startswith('-') or arg in ('-c', '-m'):
            break

        if arg.startswith('--'):
            expect_value = (arg == '--check-hash-based-pycs')
            continue

        # All short switches other than -c and -m can be combined together, including
        # those with values. So, instead of -R -B -v -Q old, we might see -RBvQ old.
        # Furthermore, the value itself can be concatenated with the switch, so rather
        # than -Q old, we might have -Qold. When switches are combined, any switch that
        # has a value "eats" the rest of the argument; for example, -RBQv is treated as
        # -R -B -Qv, and not as -R -B -Q -v. So, we need to check whether one of 'Q',
        # 'W' or 'X' was present somewhere in the arg, and whether there was anything
        # following it in the arg. If it was there but nothing followed after it, then
        # the switch is expecting a value.
        split = re.split(r'[QWX]', arg, maxsplit=1)
        expect_value = (len(split) > 1 and split[-1] != '')

    else:
        # Didn't find the target, so we don't know how to patch this command line; let
        # it run without debugging.
        return args

    if not args[i].startswith('-'):
        # If it was a filename, it can be a Python file, a directory, or a zip archive
        # that is treated as if it were a directory. However, pydevd only supports the
        # first scenario. Distinguishing between these can be tricky, and getting it
        # wrong means that process fails to launch, so be conservative.
        if not args[i].endswith('.py'):
            print('!!!', args[i])
            return args

    # Now we need to inject the ptvsd invocation right before the target. The target
    # itself can remain as is, because ptvsd is compatible with Python in that respect.
    args[i:i] = [
        '-m', 'ptvsd',
        '--server-host', 'localhost',
        '--port', '0',
        '--multiprocess',
        '--wait'
    ]

    print(args)
    return args


def patch_and_quote_args(args):
    # On Windows, pydevd expects arguments to be quoted and escaped as necessary, such
    # that simply concatenating them via ' ' produces a valid command line. This wraps
    # patch_args and applies quoting (quote_args contains platform check), so that the
    # implementation of patch_args can be kept simple.
    return pydev_monkey.quote_args(patch_args(args))
