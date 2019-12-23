# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, division, print_function, unicode_literals

import codecs
import contextlib
import json
import os
import pydevd
import socket
import sys
import threading

import ptvsd
from ptvsd import adapter
from ptvsd.common import compat, log, sockets
from ptvsd.server import options
from _pydevd_bundle.pydevd_constants import get_global_debugger
from pydevd_file_utils import get_abs_path_real_path_and_base_from_file


def _settrace(*args, **kwargs):
    log.debug("pydevd.settrace(*{0!r}, **{1!r})", args, kwargs)
    return pydevd.settrace(*args, **kwargs)


def wait_for_attach():
    log.debug("wait_for_attach()")
    dbg = get_global_debugger()
    if dbg is None:
        raise RuntimeError("wait_for_attach() called before enable_attach()")

    cancel_event = threading.Event()
    ptvsd.wait_for_attach.cancel = wait_for_attach.cancel = cancel_event.set
    pydevd._wait_for_attach(cancel=cancel_event)


def _starts_debugging(func):
    def debug(address, log_dir=None, multiprocess=True):
        if log_dir:
            log.log_dir = log_dir

        log.to_file(prefix="ptvsd.server")
        log.describe_environment("ptvsd.server debug start environment:")
        log.debug("{0}{1!r}", func.__name__, (address, log_dir, multiprocess))

        if is_attached():
            log.info("{0}() ignored - already attached.", func.__name__)
            return options.host, options.port

        # Ensure port is int
        if address is not options:
            host, port = address
            options.host, options.port = (host, int(port))

        if multiprocess is not options:
            options.multiprocess = multiprocess

        ptvsd_path, _, _ = get_abs_path_real_path_and_base_from_file(ptvsd.__file__)
        ptvsd_path = os.path.dirname(ptvsd_path)
        start_patterns = (ptvsd_path,)
        end_patterns = ("ptvsd_launcher.py",)
        log.info(
            "Won't trace filenames starting with: {0!j}\n"
            "Won't trace filenames ending with: {1!j}",
            start_patterns,
            end_patterns,
        )

        try:
            return func(start_patterns, end_patterns)
        except Exception:
            raise log.exception("{0}() failed:", func.__name__, level="info")

    return debug


@_starts_debugging
def enable_attach(dont_trace_start_patterns, dont_trace_end_patterns):
    # Errors below are logged with level="info", because the caller might be catching
    # and handling exceptions, and we don't want to spam their stderr unnecessarily.

    import subprocess

    if hasattr(enable_attach, "adapter"):
        raise AssertionError("enable_attach() can only be called once per process")

    server_access_token = compat.force_str(codecs.encode(os.urandom(32), "hex"))

    try:
        endpoints_listener = sockets.create_server("127.0.0.1", 0, timeout=5)
    except Exception as exc:
        log.exception("Can't listen for adapter endpoints:")
        raise RuntimeError("can't listen for adapter endpoints: " + str(exc))
    endpoints_host, endpoints_port = endpoints_listener.getsockname()
    log.info(
        "Waiting for adapter endpoints on {0}:{1}...", endpoints_host, endpoints_port
    )

    adapter_args = [
        sys.executable,
        os.path.dirname(adapter.__file__),
        "--for-server",
        str(endpoints_port),
        "--host",
        options.host,
        "--port",
        str(options.port),
        "--server-access-token",
        server_access_token,
    ]
    if log.log_dir is not None:
        adapter_args += ["--log-dir", log.log_dir]
    log.info("enable_attach() spawning adapter: {0!j}", adapter_args)

    # On Windows, detach the adapter from our console, if any, so that it doesn't
    # receive Ctrl+C from it, and doesn't keep it open once we exit.
    creationflags = 0
    if sys.platform == "win32":
        creationflags |= 0x08000000  # CREATE_NO_WINDOW
        creationflags |= 0x00000200  # CREATE_NEW_PROCESS_GROUP

    # Adapter will outlive this process, so we shouldn't wait for it. However, we
    # need to ensure that the Popen instance for it doesn't get garbage-collected
    # by holding a reference to it in a non-local variable, to avoid triggering
    # https://bugs.python.org/issue37380.
    try:
        enable_attach.adapter = subprocess.Popen(
            adapter_args, close_fds=True, creationflags=creationflags
        )
        if os.name == "posix":
            # It's going to fork again to daemonize, so we need to wait on it to
            # clean it up properly.
            enable_attach.adapter.wait()
        else:
            # Suppress misleading warning about child process still being alive when
            # this process exits (https://bugs.python.org/issue38890).
            enable_attach.adapter.returncode = 0
            pydevd.add_dont_terminate_child_pid(enable_attach.adapter.pid)
    except Exception as exc:
        log.exception("Error spawning debug adapter:", level="info")
        raise RuntimeError("error spawning debug adapter: " + str(exc))

    try:
        sock, _ = endpoints_listener.accept()
        try:
            sock.settimeout(None)
            sock_io = sock.makefile("rb", 0)
            try:
                endpoints = json.loads(sock_io.read().decode("utf-8"))
            finally:
                sock_io.close()
        finally:
            sockets.close_socket(sock)
    except socket.timeout:
        log.exception("Timed out waiting for adapter to connect:", level="info")
        raise RuntimeError("timed out waiting for adapter to connect")
    except Exception as exc:
        log.exception("Error retrieving adapter endpoints:", level="info")
        raise RuntimeError("error retrieving adapter endpoints: " + str(exc))

    log.info("Endpoints received from adapter: {0!j}", endpoints)

    if "error" in endpoints:
        raise RuntimeError(str(endpoints["error"]))

    try:
        host = str(endpoints["server"]["host"])
        port = int(endpoints["server"]["port"])
        options.port = int(endpoints["ide"]["port"])
    except Exception as exc:
        log.exception(
            "Error parsing adapter endpoints:\n{0!j}\n", endpoints, level="info"
        )
        raise RuntimeError("error parsing adapter endpoints: " + str(exc))
    log.info(
        "Adapter is accepting incoming IDE connections on {0}:{1}",
        options.host,
        options.port,
    )

    _settrace(
        host=host,
        port=port,
        suspend=False,
        patch_multiprocessing=options.multiprocess,
        wait_for_ready_to_run=False,
        block_until_connected=True,
        dont_trace_start_patterns=dont_trace_start_patterns,
        dont_trace_end_patterns=dont_trace_end_patterns,
        access_token=server_access_token,
        client_access_token=options.client_access_token,
    )
    log.info("pydevd is connected to adapter at {0}:{1}", host, port)
    return options.host, options.port


@_starts_debugging
def attach(dont_trace_start_patterns, dont_trace_end_patterns):
    _settrace(
        host=options.host,
        port=options.port,
        suspend=False,
        patch_multiprocessing=options.multiprocess,
        dont_trace_start_patterns=dont_trace_start_patterns,
        dont_trace_end_patterns=dont_trace_end_patterns,
        client_access_token=options.client_access_token,
    )


def is_attached():
    return pydevd._is_attached()


def break_into_debugger():
    log.debug("break_into_debugger()")

    if not is_attached():
        log.info("break_into_debugger() ignored - debugger not attached")
        return

    # Get the first frame in the stack that's not an internal frame.
    global_debugger = get_global_debugger()
    stop_at_frame = sys._getframe().f_back
    while (
        stop_at_frame is not None
        and global_debugger.get_file_type(stop_at_frame) == global_debugger.PYDEV_FILE
    ):
        stop_at_frame = stop_at_frame.f_back

    _settrace(
        suspend=True,
        trace_only_current_thread=True,
        patch_multiprocessing=False,
        stop_at_frame=stop_at_frame,
    )
    stop_at_frame = None


def debug_this_thread():
    log.debug("debug_this_thread()")
    _settrace(suspend=False)


_tls = threading.local()


def tracing(should_trace):
    pydb = get_global_debugger()

    try:
        was_tracing = _tls.is_tracing
    except AttributeError:
        was_tracing = pydb is not None

    if should_trace is None:
        return was_tracing

    # It is possible that IDE attaches after tracing is changed, but before it is
    # restored. In this case, we don't really want to restore the original value,
    # because it will effectively disable tracing for the just-attached IDE. Doing
    # the check outside the function below makes it so that if the original change
    # was a no-op because IDE wasn't attached, restore will be no-op as well, even
    # if IDE has attached by then.

    tid = threading.current_thread().ident
    if pydb is None:
        log.info("ptvsd.tracing() ignored on thread {0} - debugger not attached", tid)

        def enable_or_disable(_):
            # Always fetch the fresh value, in case it changes before we restore.
            _tls.is_tracing = get_global_debugger() is not None

    else:

        def enable_or_disable(enable):
            if enable:
                log.info("Enabling tracing on thread {0}", tid)
                pydb.enable_tracing()
            else:
                log.info("Disabling tracing on thread {0}", tid)
                pydb.disable_tracing()
            _tls.is_tracing = enable

    # Context managers don't do anything unless used in a with-statement - that is,
    # even the code up to yield won't run. But we want callers to be able to omit
    # with-statement for this function, if they don't want to restore. So, we apply
    # the change directly out here in the non-generator context, so that it happens
    # immediately - and then return a context manager that is solely for the purpose
    # of restoring the original value, which the caller can use or discard.

    @contextlib.contextmanager
    def restore_tracing():
        try:
            yield
        finally:
            enable_or_disable(was_tracing)

    enable_or_disable(should_trace)
    return restore_tracing()
