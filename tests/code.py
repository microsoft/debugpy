# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

"""Helpers to work with Python code.
"""

import re


def get_marked_line_numbers(path):
    """Given a path to a Python source file, extracts line numbers for all lines
    that are marked with #@. For example, given this file::

        print(1) #@foo
        print(2)
        print(3) #@bar

    the function will return::

        {'foo': 1, 'bar': 3}
    """

    with open(path) as f:
        lines = {}
        for i, line in enumerate(f):
            match = re.search(r'#\s*@\s*(.*?)\s*$', line)
            if match:
                marker = match.group(1)
                lines[marker] = i + 1
    return lines
