# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import pydevd
import threading
import time

from _pydevd_bundle.pydevd_comm import get_global_debugger

import ptvsd
import ptvsd.log
import ptvsd.options
from ptvsd._util import new_hidden_thread
from ptvsd.pydevd_hooks import install
from ptvsd.daemon import session_not_bound, DaemonClosedError


def _pydevd_settrace(redirect_output=None, _pydevd=pydevd, **kwargs):
    if redirect_output is not None:
        kwargs.setdefault('stdoutToServer', redirect_output)
        kwargs.setdefault('stderrToServer', redirect_output)
    # pydevd.settrace() only enables debugging of the current
    # thread and all future threads.  PyDevd is not enabled for
    # existing threads (other than the current one).  Consequently,
    # pydevd.settrace() must be called ASAP in the current thread.
    # See issue #509.
    #
    # This is tricky, however, because settrace() will block until
    # it receives a CMD_RUN message.  You can't just call it in a
    # thread to avoid blocking; doing so would prevent the current
    # thread from being debugged.
    _pydevd.settrace(**kwargs)


global_next_session = lambda: None


def enable_attach(address,
                  redirect_output=True,
                  _pydevd=pydevd,
                  _install=install,
                  on_attach=lambda: None,
                  **kwargs):

    ptvsd.main_thread = threading.current_thread()
    host, port = address

    def wait_for_connection(daemon, host, port, next_session=None):
        ptvsd.log.debug('Waiting for pydevd ...')
        debugger = get_global_debugger()
        while debugger is None:
            time.sleep(0.1)
            debugger = get_global_debugger()

        ptvsd.log.debug('Unblocking pydevd.')
        debugger.ready_to_run = True

        while True:
            session_not_bound.wait()
            try:
                global_next_session()
                on_attach()
            except DaemonClosedError:
                return

    def start_daemon():
        daemon._sock = daemon._start()
        _, next_session = daemon.start_server(addr=(host, port))
        global global_next_session
        global_next_session = next_session
        return daemon._sock

    daemon = _install(_pydevd,
                      address,
                      start_server=None,
                      start_client=(lambda daemon, h, port: start_daemon()),
                      singlesession=False,
                      **kwargs)

    ptvsd.log.debug('Starting connection listener thread')
    connection_thread = new_hidden_thread('ptvsd.listen_for_connection',
                                          wait_for_connection,
                                          args=(daemon, host, port))
    connection_thread.start()

    if ptvsd.options.no_debug:
        _setup_nodebug()
    else:
        ptvsd.log.debug('pydevd.settrace()')
        _pydevd.settrace(host=host,
                         stdoutToServer=redirect_output,
                         stderrToServer=redirect_output,
                         port=port,
                         suspend=False,
                         patch_multiprocessing=ptvsd.options.multiprocess)

    return daemon


def attach(address,
           redirect_output=True,
           _pydevd=pydevd,
           _install=install,
           **kwargs):

    ptvsd.main_thread = threading.current_thread()
    host, port = address
    daemon = _install(_pydevd, address, singlesession=False, **kwargs)

    if ptvsd.options.no_debug:
        _setup_nodebug()
    else:
        ptvsd.log.debug('pydevd.settrace()')
        _pydevd.settrace(host=host,
                         port=port,
                         stdoutToServer=redirect_output,
                         stderrToServer=redirect_output,
                         suspend=False,
                         patch_multiprocessing=ptvsd.options.multiprocess)

    return daemon


def _setup_nodebug():
    ptvsd.log.debug('Running pydevd in nodebug mode.')
    debugger = pydevd.PyDB()
    debugger.init_matplotlib_support = lambda *arg: None
    # We are invoking run() solely for side effects here - setting up the
    # debugger and connecting to our socket - so the code run is a no-op.
    debugger.run(
        file='ptvsd._remote:_nop',
        globals=None,
        locals=None,
        is_module=True,
        set_trace=False)


def _nop():
    pass
