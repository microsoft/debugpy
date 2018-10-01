# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

import threading


print_lock = threading.Lock()
real_print = print

def print(*args, **kwargs):
    """Like builtin print(), but synchronized using a global lock.
    """
    with print_lock:
        real_print(*args, **kwargs)
