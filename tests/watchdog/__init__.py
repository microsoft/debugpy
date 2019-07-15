# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

"""A watchdog process for debuggee processes spawned by tests.

Interacts with the main test runner process over stdio, and keeps track of running
ptvsd processes. If the test runner process goes down, any ptvsd test processes
are automatically killed.
"""

__all__  = ["start", "register_spawn", "unregister_spawn"]

import atexit
import os
import sys
import psutil
import subprocess

from ptvsd.common import fmt, log, messaging
from tests.watchdog import worker


_stream = None
_process = None


def start():
    global _stream, _process
    if _stream is not None:
        return

    watchdog_name = fmt("watchdog-{0}", os.getpid())
    args = [sys.executable, worker.__file__, str(os.getpid())]
    log.info(
        "Spawning {0} for tests-{1}:\n\n{2}",
        watchdog_name,
        os.getpid(),
        "\n".join(repr(s) for s in args),
    )
    _process = psutil.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE)

    _stream = messaging.JsonIOStream(_process.stdout, _process.stdin, watchdog_name)
    assert _stream.read_json() == "ready"
    atexit.register(stop)


def stop():
    if _stream is None:
        return
    _stream.write_json(["stop"])


def register_spawn(pid, name):
    if _stream is None:
        start()
    _stream.write_json(["register_spawn", pid, name])


def unregister_spawn(pid, name):
    assert _stream is not None
    _stream.write_json(["unregister_spawn", pid, name])
