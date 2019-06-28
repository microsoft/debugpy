# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import contextlib
import os


@contextlib.contextmanager
def enabled(filename):
    os.environ['PYDEVD_DEBUG'] = 'True'
    os.environ['PYDEVD_DEBUG_FILE'] = filename

    yield

    del os.environ['PYDEVD_DEBUG']
    del os.environ['PYDEVD_DEBUG_FILE']


def dump(why):
    assert why

    pydevd_debug_file = os.environ.get('PYDEVD_DEBUG_FILE')
    if not pydevd_debug_file:
        return

    try:
        f = open(pydevd_debug_file)
    except Exception:
        print('Test {0}, but no ptvsd log found'.format(why))
        return

    with f:
        print('Test {0}; dumping pydevd log:'.format(why))
        print(f.read())
