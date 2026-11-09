# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

# "force_pydevd" must be imported first to ensure (via side effects)
# that the debugpy-vendored copy of pydevd gets used. A plain import
# statement would never run it when PEP 810 lazy imports are enabled globally.
__import__("debugpy._vendored.force_pydevd")
