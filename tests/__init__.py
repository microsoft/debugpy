# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

__doc__ = """pytest-based ptvsd tests."""

import colorama
import pytest

# This is only imported to ensure that the module is actually installed and the
# timeout setting in pytest.ini is active, since otherwise most timeline-based
# tests will hang indefinitely.
import pytest_timeout # noqa


colorama.init()
pytest.register_assert_rewrite('tests.helpers')