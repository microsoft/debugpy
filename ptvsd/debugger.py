# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from ptvsd.__main__ import run_module, run_file


__author__ = "Microsoft Corporation <ptvshelp@microsoft.com>"
__version__ = "4.0.0a5"

# TODO: not needed?
DONT_DEBUG = []

RUNNERS = {
    'module': run_module,  # python -m spam
    'script': run_file,  # python spam.py
    'code': run_file,  # python -c 'print("spam")'
    None: run_file,  # catchall
}


def debug(filename, port_num, debug_id, debug_options, run_as,
          _runners=RUNNERS, *args, **kwargs):
    # TODO: docstring
    address = (None, port_num)
    try:
        run = _runners[run_as]
    except KeyError:
        # TODO: fail?
        run = _runners[None]
    run(address, filename, *args, **kwargs)
