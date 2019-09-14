# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import contextlib
import json
import os
import pydevd
import sys
import threading

import ptvsd
from ptvsd.common import log, options as common_opts
from ptvsd.server import options as server_opts
from ptvsd.common.compat import queue
from _pydevd_bundle.pydevd_constants import get_global_debugger
from pydevd_file_utils import get_abs_path_real_path_and_base_from_file


_QUEUE_TIMEOUT = 10


def wait_for_attach():
    log.info("wait_for_attach()")
    dbg = get_global_debugger()
    if not bool(dbg):
        msg = "wait_for_attach() called before enable_attach()."
        log.info(msg)
        raise AssertionError(msg)

    cancel_event = threading.Event()
    ptvsd.wait_for_attach.cancel = wait_for_attach.cancel = cancel_event.set
    pydevd._wait_for_attach(cancel=cancel_event)


def _starts_debugging(func):
    def debug(address, log_dir=None, multiprocess=True):
        if log_dir:
            common_opts.log_dir = log_dir

        log.to_file(prefix="ptvsd.server")
        log.describe_environment("ptvsd.server debug start environment:")
        log.info("{0}{1!r}", func.__name__, (address, log_dir, multiprocess))

        if is_attached():
            log.info("{0}() ignored - already attached.", func.__name__)
            return server_opts.host, server_opts.port

        # Ensure port is int
        if address is not server_opts:
            host, port = address
            server_opts.host, server_opts.port = (host, int(port))

        if multiprocess is not server_opts:
            server_opts.multiprocess = multiprocess

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
            raise log.exception("{0}() failed:", func.__name__)

    return debug


@_starts_debugging
def enable_attach(dont_trace_start_patterns, dont_trace_end_patterns):
    if hasattr(enable_attach, "called"):
        raise RuntimeError("enable_attach() can only be called once per process.")

    host, port = pydevd._enable_attach(
        ("127.0.0.1", 0),
        dont_trace_start_patterns=dont_trace_start_patterns,
        dont_trace_end_paterns=dont_trace_end_patterns,
        patch_multiprocessing=server_opts.multiprocess,
    )

    log.info("pydevd debug server running at: {0}:{1}", host, port)

    class _DAPMessagesListener(pydevd.IDAPMessagesListener):
        def before_send(self, msg):
            pass

        def after_receive(self, msg):
            try:
                if msg["command"] == "setDebuggerProperty":
                    port_queue.put(msg["arguments"]["adapterPort"])
            except KeyError:
                pass

    port_queue = queue.Queue()
    pydevd.add_dap_messages_listener(_DAPMessagesListener())

    with pydevd.skip_subprocess_arg_patch():
        import subprocess

        adapter_args = [
            sys.executable,
            os.path.join(os.path.dirname(ptvsd.__file__), "adapter"),
            "--host",
            server_opts.host,
            "--port",
            str(server_opts.port),
            "--for-server-on-port",
            str(port),
        ]

        if common_opts.log_dir is not None:
            adapter_args += ["--log-dir", common_opts.log_dir]

        log.info("enable_attach() spawning adapter: {0!r}", adapter_args)

        # Adapter life time is expected to be longer than this process,
        # so never wait on the adapter process
        process = subprocess.Popen(adapter_args, bufsize=0)
        # Ensure that we ignore the adapter process when terminating the
        # debugger. 
        pydevd.add_dont_terminate_child_pid(process.pid)

    server_opts.port = port_queue.get(True, _QUEUE_TIMEOUT)

    listener_file = os.getenv("PTVSD_LISTENER_FILE")
    if listener_file is not None:
        with open(listener_file, "w") as f:
            json.dump({"host": server_opts.host, "port": server_opts.port}, f)

    enable_attach.called = True
    log.info(
        "ptvsd debug server running at: {0}:{1}", server_opts.host, server_opts.port
    )
    return server_opts.host, server_opts.port


@_starts_debugging
def attach(dont_trace_start_patterns, dont_trace_end_patterns):
    pydevd.settrace(
        host=server_opts.host,
        port=server_opts.port,
        suspend=False,
        patch_multiprocessing=server_opts.multiprocess,
        dont_trace_start_patterns=dont_trace_start_patterns,
        dont_trace_end_paterns=dont_trace_end_patterns,
    )


def is_attached():
    return pydevd._is_attached()


def break_into_debugger():
    log.info("break_into_debugger()")

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

    pydevd.settrace(
        suspend=True,
        trace_only_current_thread=True,
        patch_multiprocessing=False,
        stop_at_frame=stop_at_frame,
    )
    stop_at_frame = None


def debug_this_thread():
    log.info("debug_this_thread()")
    pydevd.settrace(suspend=False)


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
