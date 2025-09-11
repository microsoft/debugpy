# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from importlib import import_module
import warnings

from . import check_modules, prefix_matcher, preimport, vendored

# Ensure that pydevd is our vendored copy.
_unvendored, _ = check_modules('pydevd',
                               prefix_matcher('pydev', '_pydev'))
if _unvendored:
    _unvendored = sorted(_unvendored.values())
    msg = 'incompatible copy of pydevd already imported'
    # raise ImportError(msg)
    warnings.warn(msg + ':\n {}'.format('\n  '.join(_unvendored)))

# Constants must be set before importing any other pydevd module
# due to heavy use of "from" in them.
with warnings.catch_warnings():
    warnings.simplefilter("ignore", category=DeprecationWarning)
    with vendored('pydevd'):
        pydevd_constants = import_module('_pydevd_bundle.pydevd_constants')

# Now make sure all the top-level modules and packages in pydevd are
# loaded.  Any pydevd modules that aren't loaded at this point, will
# be loaded using their parent package's __path__ (i.e. one of the
# following).
with warnings.catch_warnings():
    warnings.simplefilter("ignore", category=DeprecationWarning)
    preimport('pydevd', [
        '_pydev_bundle',
        '_pydev_runfiles',
        '_pydevd_bundle',
        '_pydevd_frame_eval',
        'pydev_ipython',
        'pydevd_plugins',
        'pydevd',
    ])
