# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

from __future__ import print_function, with_statement, absolute_import

__author__ = "Microsoft Corporation <ptvshelp@microsoft.com>"
__version__ = "4.0.0a1"

import sys

if sys.version_info >= (3,):
    from ptvsd.reraise3 import reraise
else:
    from ptvsd.reraise2 import reraise
