# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

"""Patterns that are specific to the Debug Adapter Protocol.
"""

import sys
import numbers
import py.path

from tests import code
from tests.patterns import some, _impl


id = some.int.in_range(0, 10000)
"""Matches a DAP "id", assuming some reasonable range for an implementation that
generates those ids sequentially.
"""


def source(path, **kwargs):
    """Matches DAP Source objects."""
    if isinstance(path, py.path.local):
        path = some.path(path)
    d = {"path": path}
    d.update(kwargs)
    return some.dict.containing(d)


def frame(source, line, **kwargs):
    """Matches DAP Frame objects.

    If source is py.path.local, it's automatically wrapped with some.dap.source().

    If line is str, it is treated as a line marker, and translated to a line
    number via get_marked_line_numbers(source["path"]) if possible.
    """

    # hardcode column to 1 because older versions of python don't get the
    # column number correct for exceptions
    column = 1

    if isinstance(source, py.path.local):
        source = some.dap.source(source)

    if isinstance(line, str):
        if isinstance(source, dict):
            path = source["path"]
        elif isinstance(source, _impl.DictContaining):
            path = source.items["path"]
        else:
            path = None
        assert isinstance(
            path, _impl.Path
        ), "source must be some.dap.source() to use line markers in some.dap.frame()"
        line = code.get_marked_line_numbers(path.path)[line]
       
        # If we're using python 3.11 or higher, and a line is a number, calculate the column 
        # by counting leading whitespace characters in the specified line.
        pythonVersion = sys.version_info
        if (pythonVersion[0] >= 3 and pythonVersion[1] >= 11 and isinstance(line, numbers.Number)):
            index = code.get_index_of_first_non_whitespace_char(path.path, line)
            column = index + 1

    d = {"id": some.dap.id, "source": source, "line": line, "column": column}
    d.update(kwargs)
    return some.dict.containing(d)
