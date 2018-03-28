# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import sys

# import the wrapper first, so that it gets a chance
# to detour pydevd socket functionality.
import ptvsd.wrapper


__author__ = "Microsoft Corporation <ptvshelp@microsoft.com>"
__version__ = "4.0.0a5"

DONT_DEBUG = []


def debug(filename, port_num, debug_id, debug_options, run_as):
    # TODO: docstring
    address = (None, port_num)
    if run_as == 'module':
        _run_module(address, filename)
    else:
        _run_file(address, filename)


def _run_module(address, modname):
    filename = modname + ':'
    argv = _run_argv(address, filename)
    argv.insert(argv.index('--file'), '--module')
    _run(argv)


def _run_file(address, filename):
    argv = _run_argv(address, filename)
    _run(argv)


def _run_argv(address, filename):
    host, port = address
    if host is None:
        host = '127.0.0.1'
    return [
        '--port', str(port),
        '--client', host,
        '--file', filename,
    ]


def _run(argv):
    import pydevd
    sys.argv[1:0] = argv
    try:
        pydevd.main()
    except SystemExit as ex:
        ptvsd.wrapper.ptvsd_sys_exit_code = int(ex.code)
        raise
