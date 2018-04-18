import sys
import threading
import time

import pydevd
from _pydevd_bundle.pydevd_comm import get_global_debugger

from ptvsd.pydevd_hooks import install
from ptvsd.runner import run as no_debug_runner
from ptvsd.socket import Address, create_server


########################
# high-level functions

def debug_main(address, name, kind, *extra, **kwargs):
    if kind == 'module':
        run_module(address, name, *extra, **kwargs)
    else:
        run_file(address, name, *extra, **kwargs)


def run_main(address, name, kind, *extra, **kwargs):
    no_debug_runner(address, name, kind == 'module', *extra, **kwargs)


########################
# low-level functions

def run_module(address, modname, *extra, **kwargs):
    """Run pydevd for the given module."""
    addr = Address.from_raw(address)
    run = kwargs.pop('_run', _run)
    prog = kwargs.pop('_prog', sys.argv[0])
    filename = modname + ':'
    argv = _run_argv(addr, filename, extra, _prog=prog)
    argv.insert(argv.index('--file'), '--module')
    run(argv, addr, **kwargs)


def run_file(address, filename, *extra, **kwargs):
    """Run pydevd for the given Python file."""
    addr = Address.from_raw(address)
    run = kwargs.pop('_run', _run)
    prog = kwargs.pop('_prog', sys.argv[0])
    argv = _run_argv(addr, filename, extra, _prog=prog)
    run(argv, addr, **kwargs)


def _run_argv(address, filename, extra, _prog=sys.argv[0]):
    """Convert the given values to an argv that pydevd.main() supports."""
    if '--' in extra:
        pydevd = list(extra[:extra.index('--')])
        extra = list(extra[len(pydevd) + 1:])
    else:
        pydevd = []
        extra = list(extra)

    host, port = address
    argv = [
        _prog,
        '--port', str(port),
    ]
    if not address.isserver:
        argv.extend([
            '--client', host or 'localhost',
        ])
    return argv + pydevd + [
        '--file', filename,
    ] + extra


def _run(argv, addr, _pydevd=pydevd, _install=install, **kwargs):
    """Start pydevd with the given commandline args."""
    #print(' '.join(argv))

    # Pydevd assumes that the "__main__" module is the "pydevd" module
    # and does some tricky stuff under that assumption.  For example,
    # when the debugger starts up it calls save_main_module()
    # (in pydevd_bundle/pydevd_utils.py).  That function explicitly sets
    # sys.modules["pydevd"] to sys.modules["__main__"] and then sets
    # the __main__ module to a new one.  This makes some sense since
    # it gives the debugged script a fresh __main__ module.
    #
    # This complicates things for us since we are running a different
    # file (i.e. this one) as the __main__ module.  Consequently,
    # sys.modules["pydevd"] gets set to ptvsd/__main__.py.  Subsequent
    # imports of the "pydevd" module then return the wrong module.  We
    # work around this by avoiding lazy imports of the "pydevd" module.
    # We also replace the __main__ module with the "pydevd" module here.
    if sys.modules['__main__'].__file__ != _pydevd.__file__:
        sys.modules['__main___orig'] = sys.modules['__main__']
        sys.modules['__main__'] = _pydevd

    daemon = _install(_pydevd, addr, **kwargs)
    sys.argv[:] = argv
    try:
        _pydevd.main()
    except SystemExit as ex:
        daemon.exitcode = int(ex.code)
        raise


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
        daemon.set_connection(client)

        daemon.re_build_breakpoints()
        on_attach()

    daemon = _install(_pydevd,
                      address,
                      start_server=None,
                      start_client=(lambda daemon, h, port: daemon.start()),
                      **kwargs)

    connection_thread = threading.Thread(target=wait_for_connection,
                                         args=(daemon, host, port),
                                         name='ptvsd.listen_for_connection')
    connection_thread.daemon = True
    connection_thread.start()

    _pydevd.settrace(host=host,
                     stdoutToServer=redirect_output,
                     stderrToServer=redirect_output,
                     port=port,
                     suspend=False)
