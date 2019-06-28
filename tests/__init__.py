# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

"""ptvsd tests
"""

import pkgutil
import pytest
import py.path


_tests_dir = py.path.local(__file__) / ".."

test_data = _tests_dir / "test_data"
"""A py.path.local object for the tests/test_data/ directory.

Idiomatic use is via from .. import::

    from tests import test_data
    f = open(str(test_data / "attach" / "attach1.py"))
"""


# This is only imported to ensure that the module is actually installed and the
# timeout setting in pytest.ini is active, since otherwise most timeline-based
# tests will hang indefinitely if they time out.
__import__("pytest_timeout")

# We want pytest to rewrite asserts (for better error messages) in the common code
# code used by the tests, and in all the test helpers. This does not affect ptvsd
# inside debugged processes.

def _register_assert_rewrite(modname):
    modname = str(modname)
    # print("pytest.register_assert_rewrite({0!r})".format(modname))
    pytest.register_assert_rewrite(modname)

_register_assert_rewrite("ptvsd.common")
tests_submodules = pkgutil.iter_modules([str(_tests_dir)])
for _, submodule, _ in tests_submodules:
    submodule = str("{0}.{1}".format(__name__, submodule))
    _register_assert_rewrite(submodule)

# Enable full logging to stderr, and make timestamps shorter to match maximum test
# run time better.
from ptvsd.common import log
log.stderr_levels = set(log.LEVELS)
log.timestamp_format = "06.3f"
