# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, division, print_function, unicode_literals

"""Do not import this package directly - import tests.patterns.some instead.
"""

# Wire up some.dap to be an alias for dap, to allow writing some.dap.id etc.
from tests.patterns import some
from tests.patterns import dap

some.dap = dap
