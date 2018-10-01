# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

__doc__ = """pytest-based ptvsd tests."""

import pytest

pytest.register_assert_rewrite('pytests.helpers')