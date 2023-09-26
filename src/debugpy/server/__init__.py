# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.


def adapter():
    from debugpy.server.adapters import Adapter

    return Adapter.instance
