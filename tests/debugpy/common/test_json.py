# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

"""Unit tests for debugpy.common.json numeric conversion."""

from decimal import Decimal
from fractions import Fraction

import pytest

from debugpy.common import json


class TestConverter:
    """Pins the numeric types that json._converter accepts.

    _converter deliberately narrows from numbers.Number to int and float, because
    DAP number payloads are only ever int or float. These tests guard that contract
    against accidental future widening (e.g. re-adding Decimal/complex/Fraction) or
    narrowing (e.g. dropping float).
    """

    def test_converts_int(self):
        assert json._converter("42", (int,)) == 42

    def test_converts_float(self):
        assert json._converter("3.5", (float,)) == 3.5

    def test_first_matching_type_wins(self):
        # int is listed first, so "10" is converted with int, not float.
        result = json._converter("10", (int, float))
        assert result == 10
        assert type(result) is int

    def test_returns_none_for_invalid_value(self):
        assert json._converter("not-a-number", (int,)) is None

    @pytest.mark.parametrize("classinfo_type", [Decimal, complex, Fraction])
    def test_unsupported_numeric_types_not_converted(self, classinfo_type):
        # Decimal, complex, and Fraction are numbers.Number subclasses that are
        # intentionally NOT accepted; _converter returns None instead of converting.
        assert json._converter("1", (classinfo_type,)) is None

    def test_unsupported_type_ignored_when_mixed_with_supported(self):
        # Only the supported int entry drives conversion; the Decimal entry is skipped.
        assert json._converter("7", (Decimal, int)) == 7
