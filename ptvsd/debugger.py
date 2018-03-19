# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import sys


__author__ = "Microsoft Corporation <ptvshelp@microsoft.com>"
__version__ = "4.0.0a2"

DONT_DEBUG = []


def debug(filename, port_num, debug_id, debug_options, run_as):
    # TODO: docstring

    # import the wrapper first, so that it gets a chance
    # to detour pydevd socket functionality.
    import ptvsd.wrapper
    import pydevd

    args = [
            '--port', str(port_num),
            '--client', '127.0.0.1',
            ]
    if run_as == 'module':
        args.append('--module')
        args.extend(('--file', filename + ":"))
    else:
        args.extend(('--file', filename))
    sys.argv[1:0] = args
    try:
        pydevd.main()
    except SystemExit as ex:
        ptvsd.wrapper.ptvsd_sys_exit_code = int(ex.code)
        raise
