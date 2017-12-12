# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

__author__ = "Microsoft Corporation <ptvshelp@microsoft.com>"
__version__ = "4.0.0a1"

DONT_DEBUG = []

def debug(filename, port_num, debug_id, debug_options, run_as):
    import sys
    import ptvsd.wrapper 
    import pydevd
    sys.argv[1:0] = ['--port', str(port_num), '--client', '127.0.0.1', '--file', filename]
    pydevd.main()
