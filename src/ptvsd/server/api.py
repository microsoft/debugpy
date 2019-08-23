# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import os
import sys
import pydevd
import threading

import ptvsd
from ptvsd.common import log, options as common_opts
from ptvsd.server import options as server_opts
from _pydevd_bundle.pydevd_constants import get_global_debugger
from pydevd_file_utils import (
    get_abs_path_real_path_and_base_from_file,
    get_abs_path_real_path_and_base_from_frame,
)


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

        log.to_file()
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

        return func(start_patterns, end_patterns)

    return debug


@_starts_debugging
def enable_attach(dont_trace_start_patterns, dont_trace_end_patterns):
    server_opts.host, server_opts.port = pydevd._enable_attach(
        (server_opts.host, server_opts.port),
        dont_trace_start_patterns=dont_trace_start_patterns,
        dont_trace_end_paterns=dont_trace_end_patterns,
        patch_multiprocessing=server_opts.multiprocess,
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
        and global_debugger.get_file_type(
            stop_at_frame, get_abs_path_real_path_and_base_from_frame(stop_at_frame)
        )
        == global_debugger.PYDEV_FILE
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
