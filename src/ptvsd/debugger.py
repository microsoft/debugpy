# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import sys

import ptvsd.log
from ptvsd._local import run_module, run_file, run_main


# TODO: not needed?
DONT_DEBUG = []

LOCALHOST = 'localhost'

RUNNERS = {
    'module': run_module,  # python -m spam
    'script': run_file,  # python spam.py
    'code': run_file,  # python -c 'print("spam")'
    None: run_file,  # catchall
}


def debug(filename, port_num, debug_id, debug_options, run_as,
          _runners=RUNNERS, _extra=None, *args, **kwargs):

    ptvsd.log.to_file()
    ptvsd.log.info('debug{0!r}', (filename, port_num, debug_id, debug_options, run_as))

    if _extra is None:
        _extra = sys.argv[1:]
    address = (LOCALHOST, port_num)
    try:
        run = _runners[run_as]
    except KeyError:
        # TODO: fail?
        run = _runners[None]
    if _extra:
        args = _extra + list(args)
    kwargs.setdefault('singlesession', True)
    run(address, filename, *args, **kwargs)


def run(filename, port_num, run_as,
        *args, **kwargs):

    ptvsd.log.to_file()
    ptvsd.log.info('run{0!r}', (filename, port_num, run_as))

    address = (LOCALHOST, port_num)
    run_main(address, filename, run_as, *args, **kwargs)
