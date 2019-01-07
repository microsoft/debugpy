# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

# This dummy package contains modules that are only supposed to be imported from
# the code that is executed under debugger as part of the test (e.g. via @pyfile).
# PYTHONPATH has an entry appended to it that allows these modules to be imported
# directly from such code, i.e. "import backchannel". Consequently, these modules
# should not assume that any other code from tests/ is importable.


# Ensure that __file__ is always absolute.
import os
__file__ = os.path.abspath(__file__)
