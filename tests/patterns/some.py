# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

"""Pattern matching for recursive Python data structures.

Usage::

    from tests.patterns import some

    assert object() == some.object
    assert None == some.object
    assert None != some.thing
    assert None == ~some.thing  # inverse
    assert None == some.thing | None

    assert 123 == some.thing.in_range(0, 200)
    assert "abc" == some.thing.such_that(lambda s: s.startswith("ab"))

    xs = []
    assert xs == some.specific_object(xs)  # xs is xs
    assert xs != some.specific_object([])  # xs is not []

    assert Exception() == some.instanceof(Exception)
    assert 123 == some.instanceof((int, str))
    assert "abc" == some.instanceof((int, str))

    assert True == some.bool
    assert 123.456 == some.number
    assert 123 == some.int
    assert Exception() == some.error

    assert u"abc" == some.str
    if sys.version_info < (3,):
        assert b"abc" == some.str
    else:
        assert b"abc" != some.str

    assert "abbbc" == some.str.matching(r".(b+).")
    assert "abbbc" != some.str.matching(r"bbb")

    if platform.system() == "Windows":
        assert "\\Foo\\Bar" == some.path("/foo/bar")
    else:
        assert "/Foo/Bar" != some.path("/foo/bar")

    assert {
        "bool": True,
        "list": [None, True, 123],
        "dict": {
            "int": 123,
            "str": "abc",
        },
    } == some.dict.containing({
        "list": [None, some.bool, some.int | some.str],
        "dict": some.dict.containing({
            "int": some.int.in_range(100, 200),
        })
    })
"""

__all__  = [
    "bool",
    "dap_id",
    "error",
    "instanceof",
    "int",
    "number",
    "path",
    "source",
    "str",
    "such_that",
    "thing",
]

import numbers
import sys

from ptvsd.common.compat import builtins
from tests import patterns as some


such_that = some.SuchThat
object = some.Object()
thing = some.Thing()
instanceof = some.InstanceOf
path = some.Path


bool = instanceof(builtins.bool)
number = instanceof(numbers.Real, "number")
int = instanceof(numbers.Integral, "int")
error = instanceof(Exception)


str = None
"""In Python 2, matches both str and unicode. In Python 3, only matches str.
"""
if sys.version_info < (3,):
    str = instanceof((builtins.str, builtins.unicode), "str")
else:
    str = instanceof(builtins.str)
str.matching = some.StrMatching


dict = instanceof(builtins.dict)
dict.containing = some.DictContaining


dap_id = int.in_range(0, 10000)
"""Matches a DAP "id", assuming some reasonable range for an implementation that
generates those ids sequentially.
"""


def source(path):
    """Matches "source": {"path": ...} values in DAP.
    """
    return dict.containing({"path": path})
