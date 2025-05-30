# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

"""A watchdog process for debuggee processes spawned by tests.

Interacts with the main test runner process over stdio, and keeps track of running
debugpy processes. If the test runner process goes down, any debugpy test processes
are automatically killed.
"""

__all__ = ["start", "register_spawn", "unregister_spawn"]

import atexit
import os
import psutil
import subprocess
import sys
import threading
import time

from debugpy.common import log, messaging
from tests.watchdog import worker

WATCHDOG_TIMEOUT = 10


_name = f"watchdog-{os.getpid()}"
_stream = None
_process = None
_worker_log_filename = None


def start():
    global _stream, _process, _worker_log_filename
    if _stream is not None:
        return
    if sys.version_info >= (3, 13):
        return

    args = [sys.executable, worker.__file__, str(os.getpid())]
    log.info(
        "Spawning {0} for tests-{1}:\n\n{2}",
        _name,
        os.getpid(),
        "\n".join(repr(s) for s in args),
    )

    _process = psutil.Popen(
        args, bufsize=0, stdin=subprocess.PIPE, stdout=subprocess.PIPE
    )

    _stream = messaging.JsonIOStream(_process.stdout, _process.stdin, _name)

    event, _worker_log_filename = _stream.read_json()
    assert event == "watchdog"

    atexit.register(stop)


def _dump_worker_log(command, problem, exc_info=None):
    reason = f"{_name}.{command}() {problem}"
    if _worker_log_filename is None:
        reason += ", but there is no log."
    else:
        try:
            with open(_worker_log_filename) as f:
                worker_log = f.read()
        except Exception:
            reason += f", but log {_worker_log_filename} could not be retrieved."
        else:
            reason += f"; watchdog worker process log:\n\n{worker_log}"

    if exc_info is None:
        log.error("{0}", reason)
    else:
        log.swallow_exception("{0}", reason, exc_info=exc_info)
    return reason


def _invoke(command, *args):
    def timeout():
        time.sleep(WATCHDOG_TIMEOUT)
        if timeout.occurred is None:
            reason = _dump_worker_log(command, "timed out")
            timeout.occurred = reason

    timeout.occurred = None
    timeout_thread = threading.Thread(target=timeout)
    timeout_thread.daemon = True
    timeout_thread.start()
    try:
        try:
            _stream.write_json([command] + list(args))
            response = _stream.read_json()
            assert response == ["ok"], f"{_name} {response!r}"
        finally:
            timeout.occurred = False
    except Exception:
        _dump_worker_log(command, "failed", sys.exc_info())
        raise
    else:
        assert not timeout.occurred, str(timeout.occurred)


def stop():
    if _stream is None:
        return

    try:
        _invoke("stop")
        _stream.close()
    except Exception:
        log.swallow_exception()


def register_spawn(pid, name):
    if sys.version_info >= (3, 13):
        return
    if _stream is None:
        start()
    _invoke("register_spawn", pid, name)


def unregister_spawn(pid, name):
    if sys.version_info >= (3, 13):
        return
    assert _stream is not None
    _invoke("unregister_spawn", pid, name)
