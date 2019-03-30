# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import os.path
import sys

from ptvsd.compat import unicode
from pydevd_file_utils import get_path_with_real_case


def get_test_root(name):
    tests_dir = os.path.dirname(os.path.dirname(__file__))
    p = os.path.join(tests_dir, 'func', 'testfiles', name)
    if os.path.exists(p):
        return p
    return None


def compare_path(left, right, show=True):
    # If there's a unicode/bytes mismatch, make both unicode.
    if isinstance(left, unicode):
        if not isinstance(right, unicode):
            right = right.decode(sys.getfilesystemencoding())
    elif isinstance(right, unicode):
        right = right.encode(sys.getfilesystemencoding())

    n_left = get_path_with_real_case(left)
    n_right = get_path_with_real_case(right)
    if show:
        print('LEFT : ' + n_left)
        print('RIGHT: ' + n_right)
    return n_left == n_right
