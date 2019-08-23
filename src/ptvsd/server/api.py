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


def _get_dont_trace_patterns():
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
    return start_patterns, end_patterns


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


def enable_attach(address, log_dir=None):
    if log_dir:
        common_opts.log_dir = log_dir
    log.to_file()
    log.info("enable_attach{0!r}", (address,))

    if is_attached():
        log.info("enable_attach() ignored - already attached.")
        return None, None

    # Ensure port is int
    host, port = address
    address = (host, int(port))

    start_patterns, end_patterns = _get_dont_trace_patterns()
    server_opts.host, server_opts.port = pydevd._enable_attach(
        address,
        dont_trace_start_patterns=start_patterns,
        dont_trace_end_paterns=end_patterns,
    )

    if server_opts.subprocess_notify:
        from ptvsd.server import multiproc
        multiproc.notify_root(server_opts.port)

    return (server_opts.host, server_opts.port)


def attach(address, log_dir=None):
    if log_dir:
        common_opts.log_dir = log_dir
    log.to_file()
    log.info("attach{0!r}", (address,))

    if is_attached():
        log.info("attach() ignored - already attached.")
        return

    # Ensure port is int
    host, port = address
    address = (host, int(port))
    server_opts.host, server_opts.port = address

    start_patterns, end_patterns = _get_dont_trace_patterns()

    log.debug("pydevd.settrace()")
    pydevd.settrace(
        host=host,
        port=port,
        suspend=False,
        patch_multiprocessing=server_opts.multiprocess,
        dont_trace_start_patterns=start_patterns,
        dont_trace_end_paterns=end_patterns,
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
            stop_at_frame,
            get_abs_path_real_path_and_base_from_frame(stop_at_frame)
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
