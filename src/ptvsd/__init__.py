# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

__all__ = [
    "__version__",
    "attach",
    "break_into_debugger",
    "debug_this_thread",
    "enable_attach",
    "is_attached",
    "wait_for_attach",
]


from ._version import get_versions

__version__ = get_versions()["version"]
del get_versions


from ptvsd.server import (
    attach,
    break_into_debugger,
    debug_this_thread,
    enable_attach,
    is_attached,
    wait_for_attach,
)
