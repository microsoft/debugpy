# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.


def adapter():
    """
    Returns the instance of Adapter corresponding to the debug adapter that is currently
    connected to this process, or None if there is no adapter connected. Use in lieu of
    Adapter.instance to avoid import cycles.
    """
    from debugpy.server.adapters import Adapter

    return Adapter.instance
