# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import contextlib
import os

from ptvsd.common import log


@contextlib.contextmanager
def enabled(filename):
    os.environ['PYDEVD_DEBUG'] = 'True'
    os.environ['PYDEVD_DEBUG_FILE'] = filename
    log.debug("pydevd log will be at {0}", filename)
    try:
        yield
    finally:
        del os.environ['PYDEVD_DEBUG']
        del os.environ['PYDEVD_DEBUG_FILE']


def dump(why):
    assert why

    pydevd_debug_file = os.environ.get('PYDEVD_DEBUG_FILE')
    if not pydevd_debug_file:
        return

    try:
        f = open(pydevd_debug_file)
        with f:
            pydevd_log = f.read()
    except Exception:
        log.exception("Test {0}, but pydevd log {1} could not be retrieved.", why, pydevd_debug_file)
        return

    log.info("Test {0}; pydevd log:\n\n{1}", why, pydevd_log)
