# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import os.path
import sys

import ptvsd.compat


def get_test_root(name):
    pytests_dir = os.path.dirname(os.path.dirname(__file__))
    p = os.path.join(pytests_dir, 'func', 'testfiles', name)
    if os.path.exists(p):
        return p
    return None


def compare_path(left, right, show=True):
    # If there's a unicode/bytes mismatch, make both unicode.
    if isinstance(left, ptvsd.compat.unicode):
        if not isinstance(right, ptvsd.compat.unicode):
            right = right.decode(sys.getfilesystemencoding())
    elif isinstance(right, ptvsd.compat.unicode):
        left = right.decode(sys.getfilesystemencoding())

    n_left = os.path.normcase(left)
    n_right = os.path.normcase(right)
    if show:
        print('LEFT : ' + n_left)
        print('RIGHT: ' + n_right)
    return n_left == n_right
