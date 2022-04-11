# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, division, print_function, unicode_literals

from importlib import import_module
import os

# "force_pydevd" must be imported first to ensure (via side effects)
# that the debugpy-vendored copy of pydevd gets used.
import debugpy
if debugpy.__bundling_disabled__:
    # Do what force_pydevd.py does, but using the system-provided
    # pydevd.

    # XXX: This is copied here so that the whole '_vendored' directory
    # can be deleted when DEBUGPY_BUNDLING_DISABLED is set.

    # If debugpy logging is enabled, enable it for pydevd as well
    if "DEBUGPY_LOG_DIR" in os.environ:
        os.environ[str("PYDEVD_DEBUG")] = str("True")
        os.environ[str("PYDEVD_DEBUG_FILE")] = \
            os.environ["DEBUGPY_LOG_DIR"] + str("/debugpy.pydevd.log")

    # Work around https://github.com/microsoft/debugpy/issues/346.
    # Disable pydevd frame-eval optimizations only if unset, to allow opt-in.
    if "PYDEVD_USE_FRAME_EVAL" not in os.environ:
        os.environ[str("PYDEVD_USE_FRAME_EVAL")] = str("NO")

    # Constants must be set before importing any other pydevd module
    # due to heavy use of "from" in them.
    pydevd_constants = import_module('_pydevd_bundle.pydevd_constants')
    # The default pydevd value is 1000.
    pydevd_constants.MAXIMUM_VARIABLE_REPRESENTATION_SIZE = 2 ** 32

    # When pydevd is imported it sets the breakpoint behavior, but it needs to be
    # overridden because by default pydevd will connect to the remote debugger using
    # its own custom protocol rather than DAP.
    import pydevd   # noqa
    import debugpy  # noqa

    def debugpy_breakpointhook():
        debugpy.breakpoint()

    pydevd.install_breakpointhook(debugpy_breakpointhook)

    # Ensure that pydevd uses JSON protocol
    from _pydevd_bundle import pydevd_constants
    from _pydevd_bundle import pydevd_defaults
    pydevd_defaults.PydevdCustomization.DEFAULT_PROTOCOL = pydevd_constants.HTTP_JSON_PROTOCOL
else:
    import debugpy._vendored.force_pydevd  # noqa
