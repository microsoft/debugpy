# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import threading


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
