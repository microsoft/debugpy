# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

import pytest

from ptvsd.messaging import RequestFailure

from .pattern import ANY, SUCCESS, FAILURE


VALUES = [
    None,
    True, False,
    0, -1, -1.0, 1.23,
    b'abc', b'abcd',
    u'abc', u'abcd',
    (), (1, 2, 3),
    [], [1, 2, 3],
    {}, {'a': 1, 'b': 2},
]


@pytest.mark.parametrize('x', VALUES)
def test_any(x):
    assert x == ANY


def test_lists():
    assert [1, 2, 3] == [1, ANY, 3]
    assert [1, 2, 3, 4] != [1, ANY, 4]


def test_dicts():
    assert {'a': 1, 'b': 2} == {'a': ANY, 'b': 2}
    assert {'a': 1, 'b': 2} == ANY.dict_with({'a': 1})


def test_maybe():
    def nonzero(x):
        return x != 0

    pattern = ANY.such_that(nonzero)
    assert 0 != pattern
    assert 1 == pattern
    assert 2 == pattern


def test_success():
    assert {} == SUCCESS
    assert {} != FAILURE


def test_failure():
    error = RequestFailure('error!')
    assert error != SUCCESS
    assert error == FAILURE


def test_recursive():
    assert [
        False,
        True,
        [1, 2, 3, {'aa': 4}],
        {
            'ba': [5, 6],
            'bb': [None],
            'bc': {},
            'bd': True,
            'be': [],
        }
    ] == [
        ANY,
        True,
        [1, ANY, 3, {'aa': 4}],
        ANY.dict_with({
            'ba': ANY,
            'bb': [None],
            'bc': {},
        }),
    ]
