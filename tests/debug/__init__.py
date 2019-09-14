# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, division, print_function, unicode_literals


# Expose Session directly.
def Session(*args, **kwargs):
    from tests.debug import session

    return session.Session(*args, **kwargs)
