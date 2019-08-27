# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, division, print_function, unicode_literals

import py

import ptvsd

PTVSD_DIR = py.path.local(ptvsd.__file__) / ".."
PTVSD_ADAPTER_DIR = PTVSD_DIR / "adapter"

# Added to the environment variables of all adapters and servers.
PTVSD_ENV = {"PYTHONUNBUFFERED": "1"}


# Expose Session directly.
def Session(*args, **kwargs):
    from tests.debug import session
    return session.Session(*args, **kwargs)
