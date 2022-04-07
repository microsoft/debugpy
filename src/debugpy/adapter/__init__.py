# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

__all__ = []

import os

# Force absolute path on Python 2.
__file__ = os.path.abspath(__file__)

access_token = None
"""Access token used to authenticate with this adapter."""
