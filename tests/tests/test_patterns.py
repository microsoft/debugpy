# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, division, print_function, unicode_literals

import pytest
import sys

from debugpy.common import log
from tests.patterns import some


NONE = None
NAN = float("nan")


def log_repr(x):
    s = repr(x)
    log.info("{0}", s)


VALUES = [
    object(),
    True,
    False,
    0,
    -1,
    -1.0,
    1.23,
    b"abc",
    b"abcd",
    "abc",
    "abcd",
    (),
    (1, 2, 3),
    [],
    [1, 2, 3],
    {},
    {"a": 1, "b": 2},
]


@pytest.mark.parametrize("x", VALUES)
def test_value(x):
    log_repr(some.object)
    assert x == some.object

    log_repr(some.object.equal_to(x))
    assert x == some.object.equal_to(x)

    log_repr(some.object.not_equal_to(x))
    assert x != some.object.not_equal_to(x)

    log_repr(some.object.same_as(x))
    assert x == some.object.same_as(x)

    log_repr(some.thing)
    assert x == some.thing

    log_repr(~some.thing)
    assert x != ~some.thing

    log_repr(~some.object)
    assert x != ~some.object

    log_repr(~some.object | x)
    assert x == ~some.object | x


def test_none():
    assert NONE == some.object
    assert NONE == some.object.equal_to(None)
    assert NONE == some.object.same_as(None)
    assert NONE != some.thing
    assert NONE == some.thing | None


def test_equal():
    assert 123.0 == some.object.equal_to(123)
    assert NAN != some.object.equal_to(NAN)


def test_not_equal():
    assert 123.0 != some.object.not_equal_to(123)
    assert NAN == some.object.not_equal_to(NAN)


def test_same():
    assert 123.0 != some.object.same_as(123)
    assert NAN == some.object.same_as(NAN)


def test_inverse():
    pattern = ~some.object.equal_to(2)
    log_repr(pattern)

    assert pattern == 1
    assert pattern != 2
    assert pattern == 3
    assert pattern == "2"
    assert pattern == NONE


def test_either():
    pattern = some.number | some.str
    log_repr(pattern)
    assert pattern == 123

    pattern = some.str | 123 | some.bool
    log_repr(pattern)
    assert pattern == 123


def test_in_range():
    pattern = some.int.in_range(-5, 5)
    log_repr(pattern)

    assert all([pattern == x for x in range(-5, 5)])
    assert pattern != -6
    assert pattern != 5


def test_str():
    log_repr(some.str)
    assert some.str == "abc"

    if sys.version_info < (3,):
        assert b"abc" == some.str
    else:
        assert b"abc" != some.str


def test_matching():
    pattern = some.str.matching(r".(b+).")
    log_repr(pattern)
    assert pattern == "abbbc"

    pattern = some.str.matching(r"bbb")
    log_repr(pattern)
    assert pattern != "abbbc"

    pattern = some.bytes.matching(br".(b+).")
    log_repr(pattern)
    assert pattern == b"abbbc"

    pattern = some.bytes.matching(br"bbb")
    log_repr(pattern)
    assert pattern != b"abbbc"


def test_starting_with():
    pattern = some.str.starting_with("aa")
    log_repr(pattern)
    assert pattern == "aabbbb"
    assert pattern != "bbbbaa"
    assert pattern != "bbaabb"
    assert pattern != "ababab"

    pattern = some.bytes.starting_with(b"aa")
    log_repr(pattern)
    assert pattern == b"aabbbb"
    assert pattern != b"bbbbaa"
    assert pattern != b"bbaabb"
    assert pattern != b"ababab"


def test_ending_with():
    pattern = some.str.ending_with("aa")
    log_repr(pattern)
    assert pattern == "bbbbaa"
    assert pattern == "bb\nbb\naa"
    assert pattern != "aabbbb"
    assert pattern != "bbaabb"
    assert pattern != "ababab"

    pattern = some.bytes.ending_with(b"aa")
    log_repr(pattern)
    assert pattern == b"bbbbaa"
    assert pattern == b"bb\nbb\naa"
    assert pattern != b"aabbbb"
    assert pattern != b"bbaabb"
    assert pattern != b"ababab"


def test_containing():
    pattern = some.str.containing("aa")
    log_repr(pattern)
    assert pattern == "aabbbb"
    assert pattern == "bbbbaa"
    assert pattern == "bbaabb"
    assert pattern == "bb\naa\nbb"
    assert pattern != "ababab"

    pattern = some.bytes.containing(b"aa")
    log_repr(pattern)
    assert pattern == b"aabbbb"
    assert pattern == b"bbbbaa"
    assert pattern == b"bbaabb"
    assert pattern == b"bb\naa\nbb"
    assert pattern != b"ababab"


def test_list():
    assert [1, 2, 3] == [1, some.thing, 3]
    assert [1, 2, 3, 4] != [1, some.thing, 4]

    assert [1, 2, 3, 4] == some.list.containing(1)
    assert [1, 2, 3, 4] == some.list.containing(2)
    assert [1, 2, 3, 4] == some.list.containing(3)
    assert [1, 2, 3, 4] == some.list.containing(4)
    assert [1, 2, 3, 4] == some.list.containing(1, 2)
    assert [1, 2, 3, 4] == some.list.containing(2, 3)
    assert [1, 2, 3, 4] == some.list.containing(3, 4)
    assert [1, 2, 3, 4] == some.list.containing(1, 2, 3)
    assert [1, 2, 3, 4] == some.list.containing(2, 3, 4)
    assert [1, 2, 3, 4] == some.list.containing(1, 2, 3, 4)

    assert [1, 2, 3, 4] != some.list.containing(5)
    assert [1, 2, 3, 4] != some.list.containing(1, 3)
    assert [1, 2, 3, 4] != some.list.containing(1, 2, 4)
    assert [1, 2, 3, 4] != some.list.containing(2, 3, 5)


def test_dict():
    pattern = {"a": some.thing, "b": 2}
    log_repr(pattern)
    assert pattern == {"a": 1, "b": 2}

    pattern = some.dict.containing({"a": 1})
    log_repr(pattern)
    assert pattern == {"a": 1, "b": 2}


def test_such_that():
    pattern = some.thing.such_that(lambda x: x != 1)
    log_repr(pattern)

    assert 0 == pattern
    assert 1 != pattern
    assert 2 == pattern


def test_error():
    log_repr(some.error)
    assert some.error == Exception("error!")
    assert some.error != {}


def test_recursive():
    pattern = some.dict.containing(
        {
            "dict": some.dict.containing({"int": some.int.in_range(100, 200)}),
            "list": [None, ~some.error, some.number | some.str],
        }
    )

    log_repr(pattern)

    assert pattern == {
        "list": [None, False, 123],
        "bool": True,
        "dict": {"int": 123, "str": "abc"},
    }
