import threading
import time

import pydevd
from _pydevd_bundle.pydevd_comm import get_global_debugger

from ptvsd.pydevd_hooks import install
from ptvsd.socket import create_server


# TODO: Split up enable_attach() to align with module organization.
# This should including making better use of Daemon (e,g, the
# start_server() method).
# Then move at least some parts to the appropriate modules.  This module
# is focused on running the debugger.

def enable_attach(address, redirect_output=True,
                  _pydevd=pydevd, _install=install,
                  on_attach=lambda: None, **kwargs):
    host, port = address

    def wait_for_connection(daemon, host, port):
        debugger = get_global_debugger()
        while debugger is None:
            time.sleep(0.1)
            debugger = get_global_debugger()

        debugger.ready_to_run = True
        server = create_server(host, port)
        client, _ = server.accept()
        daemon.start_session(client, 'ptvsd.Server')

        daemon.re_build_breakpoints()
        on_attach()

    daemon = _install(_pydevd,
                      address,
                      start_server=None,
                      start_client=(lambda daemon, h, port: daemon.start()),
                      singlesession=False,
                      **kwargs)

    connection_thread = threading.Thread(target=wait_for_connection,
                                         args=(daemon, host, port),
                                         name='ptvsd.listen_for_connection')
    connection_thread.pydev_do_not_trace = True
    connection_thread.is_pydev_daemon_thread = True
    connection_thread.daemon = True
    connection_thread.start()

    _pydevd.settrace(host=host,
                     stdoutToServer=redirect_output,
                     stderrToServer=redirect_output,
                     port=port,
                     suspend=False)
