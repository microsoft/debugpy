# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

__author__ = "Microsoft Corporation <ptvshelp@microsoft.com>"
__version__ = "4.0.0a1"

# ptvsd must always be imported before pydevd
import sys
assert 'pydevd' not in sys.modules

# Add our vendored pydevd directory to path, so that it gets found first.
import os.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'pydevd'))
