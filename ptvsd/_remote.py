import pydevd

from ptvsd.pydevd_hooks import install, start_server
from ptvsd.socket import Address


# TODO: Split up enable_attach() to align with module organization.
# This should including making better use of Daemon (e,g, the
# start_server() method).
# Then move at least some parts to the appropriate modules.  This module
# is focused on running the debugger.

def enable_attach(address,
                  on_attach=(lambda: None),
                  redirect_output=True,
                  _pydevd=pydevd, _install=install,
                  **kwargs):
    addr = Address.as_server(*address)
    # pydevd.settrace() forces a "client" connection, so we trick it
    # by setting start_client to start_server..
    daemon = _install(
        _pydevd,
        addr,
        start_client=start_server,
        notify_session_debugger_ready=(lambda s: on_attach()),
        singlesession=False,
        **kwargs
    )
    # Only pass the port so start_server() gets triggered.
    _pydevd.settrace(
        host=addr.host,
        stdoutToServer=redirect_output,
        stderrToServer=redirect_output,
        port=addr.port,
        suspend=False,
    )
    return daemon
