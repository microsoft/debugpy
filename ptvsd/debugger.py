# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from ptvsd.__main__ import run_module, run_file


__author__ = "Microsoft Corporation <ptvshelp@microsoft.com>"
__version__ = "4.0.0a5"

# TODO: not needed?
DONT_DEBUG = []


def debug(filename, port_num, debug_id, debug_options, run_as, **kwargs):
    # TODO: docstring
    address = ('localhost', port_num)
    if run_as == 'module':
        run_module(address, filename, **kwargs)
    else:
        run_file(address, filename, **kwargs)
