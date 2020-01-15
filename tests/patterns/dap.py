# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, division, print_function, unicode_literals

"""Patterns that are specific to the Debug Adapter Protocol.
"""

import py.path

from debugpy.common.compat import unicode
from tests import code
from tests.patterns import some, _impl


id = some.int.in_range(0, 10000)
"""Matches a DAP "id", assuming some reasonable range for an implementation that
generates those ids sequentially.
"""


def source(path, **kwargs):
    """Matches DAP Source objects.
    """
    if isinstance(path, py.path.local):
        path = some.path(path)
    d = {"path": path}
    d.update(kwargs)
    return some.dict.containing(d)


def frame(source, line, **kwargs):
    """Matches DAP Frame objects.

    If source is py.path.local, it's automatically wrapped with some.dap.source().

    If line is unicode, it is treated as a line marker, and translated to a line
    number via get_marked_line_numbers(source["path"]) if possible.
    """

    if isinstance(source, py.path.local):
        source = some.dap.source(source)

    if isinstance(line, unicode):
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

    d = {"id": some.dap.id, "source": source, "line": line, "column": 1}
    d.update(kwargs)
    return some.dict.containing(d)
