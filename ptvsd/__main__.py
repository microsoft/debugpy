# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

import argparse
import os.path
import sys


# ptvsd can also be invoked directly rather than via -m. In this case, the
# first entry on sys.path is the one added automatically by Python for the
# directory containing this file. This means that 1) import ptvsd will not
# work, since we need the parent directory of ptvsd/ to be on path, rather
# than ptvsd/ itself, and 2) many other absolute imports will break, because
# they will be resolved relative to ptvsd/ - e.g. import socket will then
# try to import ptvsd/socket.py!
#
# To fix this, we need to replace the automatically added entry such that it
# points at the parent directory instead, import ptvsd from that directory,
# and then remove than entry altogether so that it doesn't affect any further
# imports. For example, suppose the user did:
#
#   python /foo/bar/ptvsd ...
#
# At the beginning of this script, sys.path will contain '/foo/bar/ptvsd' as
# the first entry. What we want is to replace it with '/foo/bar', then import
# ptvsd with that in effect, and then remove it before continuing execution.
if __name__ == '__main__' and 'ptvsd' not in sys.modules:
    sys.path[0] = os.path.dirname(sys.path[0])
    import ptvsd # noqa
    del sys.path[0]


from ptvsd import multiproc, options
from ptvsd._attach import attach_main
from ptvsd._local import debug_main, run_main
from ptvsd.socket import Address
from ptvsd.version import __version__, __author__  # noqa


# When forming the command line involving __main__.py, it might be tempting to
# import it as a module, and then use its __file__. However, that does not work
# reliably, because __file__ can be a relative path - and when it is relative,
# that's relative to the current directory at the time import was done, which
# may be different from the current directory at the time the path is used.
#
# So, to be able to correctly locate the script at any point, we compute the
# absolute path at import time.
__file__ = os.path.abspath(__file__)


##################################
# the script

"""
For the PyDevd CLI handling see:

  https://github.com/fabioz/PyDev.Debugger/blob/master/_pydevd_bundle/pydevd_command_line_handling.py
  https://github.com/fabioz/PyDev.Debugger/blob/master/pydevd.py#L1450  (main func)
"""  # noqa

PYDEVD_OPTS = {
    '--file',
    '--vm_type',
}

PYDEVD_FLAGS = {
    '--DEBUG',
    '--DEBUG_RECORD_SOCKET_READS',
    '--cmd-line',
    '--module',
    '--print-in-debugger-startup',
    '--save-signatures',
    '--save-threading',
    '--save-asyncio',
    '--server',
    '--qt-support=auto',
}


def parse_args(argv=None):
    """Return the parsed args to use in main()."""
    if argv is None:
        argv = sys.argv
        prog = argv[0]
        if prog == __file__:
            prog = '{} -m ptvsd'.format(os.path.basename(sys.executable))
    else:
        prog = argv[0]
    argv = argv[1:]

    supported, pydevd, script = _group_args(argv)
    args = _parse_args(prog, supported)
    # '--' is used in _run_args to extract pydevd specific args
    extra = pydevd + ['--']
    if script:
        extra += script
    return args, extra


def _group_args(argv):
    supported = []
    pydevd = []
    script = []

    try:
        pos = argv.index('--')
    except ValueError:
        script = []
    else:
        script = argv[pos + 1:]
        argv = argv[:pos]

    for arg in argv:
        if arg == '-h' or arg == '--help':
            return argv, [], script

    gottarget = False
    skip = 0
    for i in range(len(argv)):
        if skip:
            skip -= 1
            continue

        arg = argv[i]
        try:
            nextarg = argv[i + 1]
        except IndexError:
            nextarg = None

        # TODO: Deprecate the PyDevd arg support.
        # PyDevd support
        if gottarget:
            script = argv[i:] + script
            break
        if arg == '--file':
            if nextarg is None:  # The filename is missing...
                pydevd.append(arg)
                continue  # This will get handled later.
            if nextarg.endswith(':') and '--module' in pydevd:
                pydevd.remove('--module')
                arg = '-m'
                argv[i + 1] = nextarg = nextarg[:-1]
            else:
                arg = nextarg
                skip += 1

        if arg in PYDEVD_OPTS:
            pydevd.append(arg)
            if nextarg is not None:
                pydevd.append(nextarg)
            skip += 1
        elif arg in PYDEVD_FLAGS:
            pydevd.append(arg)
        elif arg == '--nodebug':
            supported.append(arg)

        # ptvsd support
        elif arg in ('--host', '--port', '--pid', '-m', '-c', '--subprocess-of', '--subprocess-notify'):
            if arg in ('-m', '-c', '--pid'):
                gottarget = True
            supported.append(arg)
            if nextarg is not None:
                supported.append(nextarg)
            skip += 1
        elif arg in ('--single-session', '--wait', '--client'):
            supported.append(arg)
        elif arg == '--multiprocess':
            supported.append(arg)
            pydevd.append(arg)
        elif not arg.startswith('-'):
            supported.append(arg)
            gottarget = True

        # unsupported arg
        else:
            supported.append(arg)
            break

    return supported, pydevd, script


def _parse_args(prog, argv):
    parser = argparse.ArgumentParser(prog=prog)

    parser.add_argument('--nodebug', action='store_true')
    parser.add_argument('--client', action='store_true')

    parser.add_argument('--host', required=True)
    parser.add_argument('--port', type=int, required=True)

    def port_range(arg):
        arg = tuple(int(s) for s in arg.split('-'))
        if len(arg) != 2:
            raise ValueError
        return arg

    parser.add_argument('--multiprocess', action='store_true')
    parser.add_argument('--subprocess-of', type=int, help=argparse.SUPPRESS)
    parser.add_argument('--subprocess-notify', type=int, help=argparse.SUPPRESS)

    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument('-m', dest='module')
    target.add_argument('-c', dest='code')
    target.add_argument('--pid', type=int)
    target.add_argument('filename', nargs='?')

    parser.add_argument('--single-session', action='store_true')
    parser.add_argument('--wait', action='store_true')

    parser.add_argument('-V', '--version', action='version')
    parser.version = __version__

    args = parser.parse_args(argv)
    ns = vars(args)

    host = ns.pop('host', None)
    port = ns.pop('port')
    client = ns.pop('client')
    args.address = (Address.as_client if client else Address.as_server)(host, port) # noqa

    if ns['multiprocess']:
        options.multiprocess = True
        multiproc.listen_for_subprocesses()

    options.subprocess_of = ns.pop('subprocess_of')
    options.subprocess_notify = ns.pop('subprocess_notify')

    pid = ns.pop('pid')
    module = ns.pop('module')
    filename = ns.pop('filename')
    code = ns.pop('code')
    if pid is not None:
        args.name = pid
        args.kind = 'pid'
    elif module is not None:
        args.name = module
        args.kind = 'module'
    elif code is not None:
        options.code = code
        args.name = 'ptvsd.run_code'
        args.kind = 'module'
    else:
        args.name = filename
        args.kind = 'script'

    return args


def handle_args(addr, name, kind, extra=(), nodebug=False, **kwargs):
    if kind == 'pid':
        attach_main(addr, name, *extra, **kwargs)
    elif nodebug:
        run_main(addr, name, kind, *extra, **kwargs)
    else:
        debug_main(addr, name, kind, *extra, **kwargs)


def main(argv=None):
    args, extra = parse_args(argv)
    handle_args(args.address, args.name, args.kind, extra,
                nodebug=args.nodebug, singlesession=args.single_session,
                wait=args.wait)


if __name__ == '__main__':
    main()
