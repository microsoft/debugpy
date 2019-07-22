# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

"""An implementation of the Debug Adapter Protocol (DAP) for Python.

https://microsoft.github.io/debug-adapter-protocol/
"""

__all__ = [
    "__version__",
    "attach",
    "break_into_debugger",
    "debug_this_thread",
    "enable_attach",
    "is_attached",
    "wait_for_attach",
]

import codecs
from os import path

# Force absolute path on Python 2.
__file__ = path.abspath(__file__)

# Preload encodings that we're going to use to avoid import deadlocks on Python 2.
codecs.lookup("ascii")
codecs.lookup("utf8")
codecs.lookup("utf-8")
codecs.lookup("latin1")
codecs.lookup("latin-1")

from ptvsd import _version

__version__ = _version.get_versions()["version"]
del _version

from ptvsd.server.attach_server import (
    attach,
    break_into_debugger,
    debug_this_thread,
    enable_attach,
    is_attached,
    wait_for_attach,
)
