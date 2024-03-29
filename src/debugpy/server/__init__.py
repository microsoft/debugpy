# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import itertools
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    import debugpy.server.adapters as adapters

# Unique IDs for DAP objects such as threads, variables, breakpoints etc. These are
# negative to allow for pre-existing OS-assigned IDs (which are positive) to be used
# where available, e.g. for threads.
_dap_ids = itertools.count(-1, -1)


def new_dap_id() -> int:
    """Returns the next unique ID."""
    return next(_dap_ids)


def adapter() -> Optional["adapters.Adapter"]:
    """
    Returns the instance of Adapter corresponding to the debug adapter that is currently
    connected to this process, or None if there is no adapter connected. Use in lieu of
    Adapter.instance to avoid import cycles.
    """
    from debugpy.server.adapters import Adapter

    return Adapter.instance
