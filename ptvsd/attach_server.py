# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import threading

# TODO: Why import run_module & run_file?
from ptvsd._main import (  # noqa
    run_module, run_file, enable_attach as ptvsd_enable_attach,
)
import pydevd

# TODO: Why import these?
from _pydevd_bundle.pydevd_custom_frames import (  # noqa
    CustomFramesContainer, custom_frames_container_init,
)
from _pydevd_bundle.pydevd_additional_thread_info import (
    PyDBAdditionalThreadInfo,
)
from _pydevd_bundle.pydevd_comm import (
    get_global_debugger, CMD_THREAD_SUSPEND,
)

DEFAULT_HOST = '0.0.0.0'
DEFAULT_PORT = 5678

_attached = threading.Event()


def wait_for_attach(timeout=None):
    """If a remote debugger is attached, returns immediately. Otherwise,
    blocks until a remote debugger attaches to this process, or until the
    optional timeout occurs.

    Parameters
    ----------
    timeout : float, optional
        The timeout for the operation in seconds (or fractions thereof).
    """
    _attached.wait(timeout)


def enable_attach(address=(DEFAULT_HOST, DEFAULT_PORT), redirect_output=True):
    """Enables a client to attach to this process remotely to debug Python code.

    Parameters
    ----------
    address : (str, int), optional
        Specifies the interface and port on which the debugging server should
        listen for TCP connections. It is in the same format as used for
        regular sockets of the `socket.AF_INET` family, i.e. a tuple of
        ``(hostname, port)``. On client side, the server is identified by the
        Qualifier string in the usual ``'hostname:port'`` format, e.g.:
        ``'myhost.cloudapp.net:5678'``. Default is ``('0.0.0.0', 5678)``.
    redirect_output : bool, optional
        Specifies whether any output (on both `stdout` and `stderr`) produced
        by this program should be sent to the debugger. Default is ``True``.

    Notes
    -----
    This function returns immediately after setting up the debugging server,
    and does not block program execution. If you need to block until debugger
    is attached, call `ptvsd.wait_for_attach`. The debugger can be detached
    and re-attached multiple times after `enable_attach` is called.

    Only the thread on which this function is called, and any threads that are
    created after it returns, will be visible in the debugger once it is
    attached. Any threads that are already running before this function is
    called will not be visible.
    """
    if get_global_debugger() is not None:
        return
    _attached.clear()
    ptvsd_enable_attach(address, redirect_output, on_attach=_attached.set)


def is_attached():
    """Returns ``True`` if debugger is attached, ``False`` otherwise."""
    return _attached.isSet()


def break_into_debugger():
    """If a remote debugger is attached, pauses execution of all threads,
    and breaks into the debugger with current thread as active.
    """
    debugger = get_global_debugger()
    if not _attached.isSet() or debugger is None:
        return

    thread = pydevd.threadingCurrentThread()
    try:
        additional_info = thread.additional_info
    except AttributeError:
        additional_info = PyDBAdditionalThreadInfo()
        thread.additional_info = additional_info

    debugger.set_suspend(thread, CMD_THREAD_SUSPEND)
