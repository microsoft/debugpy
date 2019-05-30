# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import pydevd
import time

from _pydevd_bundle.pydevd_comm import get_global_debugger

import ptvsd
import ptvsd.server.log
import ptvsd.server.options
from ptvsd.server._util import new_hidden_thread
from ptvsd.server.pydevd_hooks import install
from ptvsd.server.daemon import session_not_bound, DaemonClosedError


global_next_session = lambda: None


def enable_attach(address, on_attach=lambda: None, **kwargs):

    host, port = address

    def wait_for_connection(daemon, host, port, next_session=None):
        ptvsd.server.log.debug('Waiting for pydevd ...')
        debugger = get_global_debugger()
        while debugger is None:
            time.sleep(0.1)
            debugger = get_global_debugger()

        ptvsd.server.log.debug('Unblocking pydevd.')
        debugger.ready_to_run = True

        while True:
            try:
                session_not_bound.wait()
                try:
                    global_next_session()
                    on_attach()
                except DaemonClosedError:
                    return
            except TypeError:
                # May happen during interpreter shutdown
                # (if some global -- such as global_next_session becomes None).
                return

    def start_daemon():
        daemon._sock = daemon._start()
        _, next_session = daemon.start_server(addr=(host, port))
        global global_next_session
        global_next_session = next_session
        return daemon._sock

    daemon = install(pydevd,
                     address,
                     start_server=None,
                     start_client=(lambda daemon, h, port: start_daemon()),
                     singlesession=False,
                     **kwargs)

    ptvsd.server.log.debug('Starting connection listener thread')
    connection_thread = new_hidden_thread('ptvsd.server.listen_for_connection',
                                          wait_for_connection,
                                          args=(daemon, host, port))
    connection_thread.start()

    if ptvsd.server.options.no_debug:
        _setup_nodebug()
    else:
        ptvsd.server.log.debug('pydevd.settrace()')
        pydevd.settrace(host=host,
                        port=port,
                        suspend=False,
                        patch_multiprocessing=ptvsd.server.options.multiprocess)

    return daemon


def attach(address, **kwargs):
    host, port = address
    daemon = install(pydevd, address, singlesession=False, **kwargs)

    if ptvsd.server.options.no_debug:
        _setup_nodebug()
    else:
        ptvsd.server.log.debug('pydevd.settrace()')
        pydevd.settrace(host=host,
                        port=port,
                        suspend=False,
                        patch_multiprocessing=ptvsd.server.options.multiprocess)

    return daemon


def _setup_nodebug():
    ptvsd.server.log.debug('Running pydevd in nodebug mode.')
    debugger = pydevd.PyDB()
    debugger.init_matplotlib_support = lambda *arg: None
    # We are invoking run() solely for side effects here - setting up the
    # debugger and connecting to our socket - so the code run is a no-op.
    debugger.run(
        file='ptvsd.server._remote:_nop',
        globals=None,
        locals=None,
        is_module=True,
        set_trace=False)


def _nop():
    pass
