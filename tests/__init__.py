# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, division, print_function, unicode_literals

"""debugpy tests
"""

import os
import pkgutil
import py
import pytest

# Do not import anything from debugpy until assert rewriting is enabled below!

full = int(os.environ.get("DEBUGPY_TESTS_FULL", "0")) != 0

root = py.path.local(__file__) / ".."

test_data = root / "test_data"
"""A py.path.local object for the tests/test_data/ directory.

Idiomatic use is via from .. import::

    from tests import test_data
    f = open(str(test_data / "attach" / "attach1.py"))
"""


# This is only imported to ensure that the module is actually installed and the
# timeout setting in pytest.ini is active, since otherwise most timeline-based
# tests will hang indefinitely if they time out.
import pytest_timeout  # noqa


# We want pytest to rewrite asserts (for better error messages) in the common code
# code used by the tests, and in all the test helpers. This does not affect debugpy
# inside debugged processes.


def _register_assert_rewrite(modname):
    modname = str(modname)
    # print("pytest.register_assert_rewrite({0!r})".format(modname))
    pytest.register_assert_rewrite(modname)


_register_assert_rewrite("debugpy.common")
tests_submodules = pkgutil.iter_modules([str(root)])
for _, submodule, _ in tests_submodules:
    submodule = str("{0}.{1}".format(__name__, submodule))
    _register_assert_rewrite(submodule)


# Now we can import these, and pytest will rewrite asserts in them.
from debugpy.common import json, log
import debugpy.server  # noqa

# Clean up environment variables that were automatically set when importing pydevd -
# we don't need them in the test runner process (since pydevd is not tracing it),
# and some tests must be able to spawn debuggee with them unset.
for name in (
    "DEBUGPY_LOG_DIR",
    "PYDEVD_DEBUG",
    "PYDEVD_DEBUG_FILE",
    "PYDEVD_USE_FRAME_EVAL",
):
    os.environ.pop(name, None)

# Enable full logging to stderr, and make timestamps shorter to match maximum test
# run time better.
log.stderr.levels = all
log.timestamp_format = "06.3f"
log.to_file(prefix="tests")


# Enable JSON serialization for py.path.local.
def json_default(self, obj):
    if isinstance(obj, py.path.local):
        return obj.strpath
    return self.original_default(obj)


json.JsonEncoder.original_default = json.JsonEncoder.default
json.JsonEncoder.default = json_default
