# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

"""
Object inspection: rendering values, enumerating children etc.

This module provides a generic non-DAP-aware API with minimal dependencies, so that
it can be unit-tested in isolation without requiring a live debugpy session.

debugpy.server.eval then wraps it in DAP-specific adapter classes that expose the
same functionality in DAP terms.
"""

import sys
from dataclasses import dataclass
from typing import Optional


@dataclass
class ValueFormat:
    hex: bool = False
    """Whether integers should be rendered in hexadecimal."""

    max_length: int = sys.maxsize
    """
    Maximum length of the string representation of variable values.
    """

    truncation_suffix: str = ""
    """Suffix to append to string representation of value when truncation occurs.
    Counts towards max_value_length and max_key_length."""

    circular_ref_marker: Optional[str] = None
    """
    String to use for nested circular references (e.g. list containing itself). If None,
    circular references aren't detected and the caller is responsible for avoiding them
    in inputs.
    """
    