# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

__author__ = "Microsoft Corporation <ptvshelp@microsoft.com>"
__version__ = "4.0.0a1"

import sys
import os.path

# ptvsd must always be imported before pydevd
if 'pydevd' in sys.modules:
    raise ImportError('ptvsd must be imported before pydevd')

# Add our vendored pydevd directory to path, so that it gets found first.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'pydevd'))

# Load our wrapper module, which will detour various functionality inside pydevd.
# This must be done before the imports below, otherwise some modules will end up
# with local copies of pre-detour functions.
import ptvsd.wrapper

# Now make sure all the top-level modules and packages in pydevd are loaded.
import _pydev_bundle
import _pydev_imps
import _pydev_runfiles
import _pydevd_bundle
import _pydevd_frame_eval
import pydev_ipython
import pydevd_concurrency_analyser
import pydevd_plugins
import pydevd

# Remove sys.path entry added above - any pydevd modules that aren't loaded at
# this point, will be loaded using their parent package's __path__.
del sys.path[0]
