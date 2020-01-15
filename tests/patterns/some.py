# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, division, print_function, unicode_literals

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
    assert object() == some.object.same_as(object())

    assert b"abc" == some.bytes
    assert u"abc" == some.str
    if sys.version_info < (3,):
        assert b"abc" == some.str
    else:
        assert b"abc" != some.str

    assert "abbc" == some.str.starting_with("ab")
    assert "abbc" == some.str.ending_with("bc")
    assert "abbc" == some.str.containing("bb")

    assert "abbc" == some.str.matching(r".(b+).")
    assert "abbc" != some.str.matching(r"ab")
    assert "abbc" != some.str.matching(r"bc")

    if sys.platform == "win32":
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

__all__ = [
    "bool",
    "bytes",
    "dap",
    "dict",
    "error",
    "instanceof",
    "int",
    "list",
    "number",
    "path",
    "str",
    "thing",
    "tuple",
]

import numbers
import re
import sys

from debugpy.common.compat import builtins
from tests.patterns import _impl


object = _impl.Object()
thing = _impl.Thing()
instanceof = _impl.InstanceOf
path = _impl.Path


bool = instanceof(builtins.bool)
number = instanceof(numbers.Real, "number")
int = instanceof(numbers.Integral, "int")
tuple = instanceof(builtins.tuple)
error = instanceof(Exception)


bytes = instanceof(builtins.bytes)
bytes.starting_with = lambda prefix: bytes.matching(
    re.escape(prefix) + b".*", re.DOTALL
)
bytes.ending_with = lambda suffix: bytes.matching(b".*" + re.escape(suffix), re.DOTALL)
bytes.containing = lambda sub: bytes.matching(b".*" + re.escape(sub) + b".*", re.DOTALL)


"""In Python 2, matches both str and unicode. In Python 3, only matches str.
"""
if sys.version_info < (3,):
    str = instanceof((builtins.str, builtins.unicode), "str")
else:
    str = instanceof(builtins.str)

str.starting_with = lambda prefix: str.matching(re.escape(prefix) + ".*", re.DOTALL)
str.ending_with = lambda suffix: str.matching(".*" + re.escape(suffix), re.DOTALL)
str.containing = lambda sub: str.matching(".*" + re.escape(sub) + ".*", re.DOTALL)


list = instanceof(builtins.list)
list.containing = _impl.ListContaining


dict = instanceof(builtins.dict)
dict.containing = _impl.DictContaining


# Set in __init__.py to avoid circular dependency.
dap = None
