# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import sys

import ptvsd.wrapper


__author__ = "Microsoft Corporation <ptvshelp@microsoft.com>"
__version__ = "4.0.0a5"


def run_module(address, modname, **kwargs):
    """Run pydevd for the given module."""
    filename = modname + ':'
    argv = _run_argv(address, filename)
    argv.insert(argv.index('--file'), '--module')
    _run(argv, **kwargs)


def run_file(address, filename, **kwargs):
    """Run pydevd for the given Python file."""
    argv = _run_argv(address, filename)
    _run(argv, **kwargs)


def _run_argv(address, filename):
    """Convert the given values to an argv that pydevd.main() supports."""
    host, port = address
    if host is None:
        host = '127.0.0.1'
    return [
        sys.argv[0],
        '--port', str(port),
        '--client', host,
        '--file', filename,
    ]


def _run(argv, **kwargs):
    """Start pydevd with the given commandline args."""
    pydevd = ptvsd.wrapper.install(**kwargs)
    sys.argv[:] = argv
    try:
        pydevd.main()
    except SystemExit as ex:
        ptvsd.wrapper.ptvsd_sys_exit_code = int(ex.code)
        raise


##################################
# the script

def main():
    _run(sys.argv)


if __name__ == '__main__':
    main()
