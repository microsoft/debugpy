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

# Force absolute path on Python 2.
from os import path
__file__ = path.abspath(__file__)
del path

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
