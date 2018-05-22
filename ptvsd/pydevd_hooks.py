import sys
import threading

from _pydevd_bundle import pydevd_comm

from ptvsd.socket import Address
from ptvsd.daemon import Daemon, DaemonStoppedError, DaemonClosedError
from ptvsd._util import debug


def start_server(daemon, host, port):
    """Return a socket to a (new) local pydevd-handling daemon.

    The daemon supports the pydevd client wire protocol, sending
    requests and handling responses (and events).

    This is a replacement for _pydevd_bundle.pydevd_comm.start_server.
    """
    pydevd, next_session = daemon.start_server((host, port))

    def handle_next():
        try:
            session = next_session()
            debug('done waiting')
            return session
        except (DaemonClosedError, DaemonStoppedError):
            # Typically won't happen.
            debug('stopped')
            raise
        except Exception as exc:
            # TODO: log this?
            debug('failed:', exc, tb=True)
            return None

    while True:
        debug('waiting on initial connection')
        handle_next()
        break

    def serve_forever():
        while True:
            debug('waiting on next connection')
            try:
                handle_next()
            except (DaemonClosedError, DaemonStoppedError):
                break
        debug('done')
    t = threading.Thread(
        target=serve_forever,
        name='ptvsd.sessions',
        )
    t.daemon = True,
    t.start()
    return pydevd


def start_client(daemon, host, port):
    """Return a socket to an existing "remote" pydevd-handling daemon.

    The daemon supports the pydevd client wire protocol, sending
    requests and handling responses (and events).

    This is a replacement for _pydevd_bundle.pydevd_comm.start_client.
    """
    pydevd, start_session = daemon.start_client((host, port))
    start_session()
    return pydevd


def install(pydevd, address,
            start_server=start_server, start_client=start_client,
            **kwargs):
    """Configure pydevd to use our wrapper.

    This is a bit of a hack to allow us to run our VSC debug adapter
    in the same process as pydevd.  Note that, as with most hacks,
    this is somewhat fragile (since the monkeypatching sites may
    change).
    """
    addr = Address.from_raw(address)
    daemon = Daemon(**kwargs)

    _start_server = (lambda p: start_server(daemon, addr.host, p))
    _start_server.orig = start_server
    _start_client = (lambda h, p: start_client(daemon, h, p))
    _start_client.orig = start_client

    # These are the functions pydevd invokes to get a socket to the client.
    pydevd_comm.start_server = _start_server
    pydevd_comm.start_client = _start_client

    # Ensure that pydevd is using our functions.
    pydevd.start_server = _start_server
    pydevd.start_client = _start_client
    __main__ = sys.modules['__main__']
    if __main__ is not pydevd and __main__.__file__ == pydevd.__file__:
        __main__.start_server = _start_server
        __main__.start_client = _start_client
    return daemon
