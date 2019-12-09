# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, division, print_function, unicode_literals

"""An implementation of the Debug Adapter Protocol (DAP) for Python.

https://microsoft.github.io/debug-adapter-protocol/
"""

__all__ = [
    "__version__",
    "attach",
    "break_into_debugger",
    "debug_this_thread",
    "enable_attach",
    "is_attached",
    "wait_for_attach",
    "tracing",
]

import codecs
import os

from ptvsd import _version


# Expose ptvsd.server API from subpackage, but do not actually import it unless
# and until a member is invoked - we don't want the server package loaded in the
# adapter, the tests, or setup.py.

# Docstrings for public API members must be formatted according to PEP 8 - no more
# than 72 characters per line! - and must be readable when retrieved via help().


def wait_for_attach():
    """If an IDE is connected to the debug server in this process,
    returns immediately. Otherwise, blocks until an IDE connects.

    While this function is waiting, it can be canceled by calling
    wait_for_attach.cancel().
    """

    from ptvsd.server import api

    return api.wait_for_attach()


def enable_attach(address, log_dir=None, multiprocess=True):
    """Starts a DAP (Debug Adapter Protocol) server in this process,
    listening for incoming socket connection from the IDE on the
    specified address.

    address must be a (host, port) tuple, as defined by the standard
    socket module for the AF_INET address family.

    If specified, log_dir must be a path to some existing directory;
    the debugger will then create its log files in that directory.
    A separate log file is created for every process, to accommodate
    scenarios involving multiple processes. The log file for a process
    with process ID <pid> will be named "ptvsd_<pid>.log".

    If multiprocess is true, ptvsd will also intercept child processes
    spawned by this process, inject a debug server into them, and
    configure it to attach to the same IDE before the child process
    starts running any user code.

    Returns the interface and the port on which the debug server is
    actually listening, in the same format as address. This may be
    different from address if port was 0 in the latter, in which case
    the server will pick some unused ephemeral port to listen on.

    This function does't wait for the IDE to connect to the debug server
    that it starts. Use wait_for_attach() to block execution until the
    IDE connects.
    """

    from ptvsd.server import api

    return api.enable_attach(address, log_dir)


def attach(address, log_dir=None, multiprocess=True):
    """Starts a DAP (Debug Adapter Protocol) server in this process,
    and connects it to the IDE that is listening for an incoming
    connection on a socket with the specified address.

    address must be a (host, port) tuple, as defined by the standard
    socket module for the AF_INET address family.

    If specified, log_dir must be a path to some existing directory;
    the debugger will then create its log files in that directory.
    A separate log file is created for every process, to accommodate
    scenarios involving multiple processes. The log file for a process
    with process ID <pid> will be named "ptvsd_<pid>.log".

    If multiprocess is true, ptvsd will also intercept child processes
    spawned by this process, inject a debug server into them, and
    configure it to attach to the same IDE before the child process
    starts running any user code.

    This function doesn't return until connection to the IDE has been
    established.
    """

    from ptvsd.server import api

    return api.attach(address, log_dir)


def is_attached():
    """True if an IDE is connected to the debug server in this process.
    """

    from ptvsd.server import api

    return api.is_attached()


def break_into_debugger():
    """If the IDE is connected, pauses execution of all threads, and
    breaks into the debugger with current thread as active.
    """

    from ptvsd.server import api

    return api.break_into_debugger()


def debug_this_thread():
    """Tells debugger to start tracing the current thread.

    Must be called on any background thread that is started by means
    other than the usual Python APIs (i.e. the "threading" module),
    for breakpoints to work on that thread.
    """

    from ptvsd.server import api

    return api.debug_this_thread()


def tracing(should_trace=None):
    """Enables or disables tracing on this thread. When called without an
    argument, returns the current tracing state.
    When tracing is disabled, breakpoints will not be hit, but code executes
    significantly faster.
    If debugger is not attached, this function has no effect.
    This function can also be used in a with-statement to automatically save
    and then restore the previous tracing setting::
        with ptvsd.tracing(False):
            # Tracing disabled
            ...
            # Tracing restored
    Parameters
    ----------
    should_trace : bool, optional
        Whether to enable or disable tracing.
    """
    from ptvsd.server import api

    return api.tracing(should_trace)


__version__ = _version.get_versions()["version"]

# Force absolute path on Python 2.
__file__ = os.path.abspath(__file__)

# Preload encodings that we're going to use to avoid import deadlocks on Python 2,
# before importing anything from ptvsd.
map(codecs.lookup, ["ascii", "utf8", "utf-8", "latin1", "latin-1", "idna", "hex"])
