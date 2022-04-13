# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

"""Helpers to work with Python code.
"""

import py.path
import re

_marked_line_numbers_cache = {}


def get_marked_line_numbers(path):
    """Given a path to a Python source file, extracts line numbers for all lines
    that are marked with #@. For example, given this file::

        print(1)  # @foo
        print(2)
        print(3)  # @bar,baz

    the function will return::

        {"foo": 1, "bar": 3, "baz": 3}
    """

    if isinstance(path, py.path.local):
        path = path.strpath

    try:
        return _marked_line_numbers_cache[path]
    except KeyError:
        pass

    # Read as bytes to avoid decoding errors.
    with open(path, "rb") as f:
        lines = {}
        for i, line in enumerate(f):
            match = re.search(rb"#\s*@(.+?)\s*$", line)
            if match:
                markers = match.group(1).decode("ascii")
                for marker in markers.split(","):
                    lines[marker] = i + 1

    _marked_line_numbers_cache[path] = lines
    return lines
