# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

"""ptvsd tests
"""

import json
import pkgutil
import pytest
import py.path
import sys

# Do not import anything from ptvsd until assert rewriting is enabled below!


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
__import__("pytest_timeout")


# We want pytest to rewrite asserts (for better error messages) in the common code
# code used by the tests, and in all the test helpers. This does not affect ptvsd
# inside debugged processes.

def _register_assert_rewrite(modname):
    modname = str(modname)
    # print("pytest.register_assert_rewrite({0!r})".format(modname))
    pytest.register_assert_rewrite(modname)

_register_assert_rewrite("ptvsd.common")
tests_submodules = pkgutil.iter_modules([str(root)])
for _, submodule, _ in tests_submodules:
    submodule = str("{0}.{1}".format(__name__, submodule))
    _register_assert_rewrite(submodule)


# Now we can import these, and pytest will rewrite asserts in them.
from ptvsd.common import fmt, log, messaging


# Enable full logging to stderr, and make timestamps shorter to match maximum test
# run time better.
log.stderr = sys.stderr  # use pytest-captured stderr rather than __stderr__
log.stderr_levels = set(log.LEVELS)
log.timestamp_format = "06.3f"


# Enable JSON serialization for py.path.local

class JSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, py.path.local):
            return obj.strpath
        return super(JSONEncoder, self).default(obj)

fmt.JsonObject.json_encoder = JSONEncoder(indent=4)
fmt.JsonObject.json_encoder_factory = JSONEncoder
messaging.JsonIOStream.json_encoder_factory = JSONEncoder
