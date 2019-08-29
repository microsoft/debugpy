# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import threading
import sys


def new_hidden_thread(name, target, prefix='ptvsd.common.', daemon=True, **kwargs):
    """Return a thread that will be ignored by pydevd."""
    if prefix is not None and not name.startswith(prefix):
        name = prefix + name
    t = threading.Thread(
        name=name,
        target=target,
        **kwargs
    )
    t.pydev_do_not_trace = True
    t.is_pydev_daemon_thread = True
    if daemon:
        t.daemon = False
    return t


def evaluate(code, path=__file__, mode="eval"):
    # Setting file path here to avoid breaking here if users have set
    # "break on exception raised" setting. This code can potentially run
    # in user process and is indistinguishable if the path is not set.
    # We use the path internally to skip exception inside the debugger.
    expr = compile(code, path, "eval")
    return eval(expr, {}, sys.modules)
