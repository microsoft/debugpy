# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

import pytest

from ptvsd.messaging import RequestFailure

from .pattern import Pattern, ANY, SUCCESS, FAILURE


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
def test_eq(x):
    assert x in Pattern(x)


@pytest.mark.parametrize('xy', zip(VALUES[1:], VALUES[:-1]))
def test_ne(xy):
    x, y = xy
    if x != y:
        assert x not in Pattern(y)

@pytest.mark.parametrize('x', VALUES)
def test_any(x):
    assert x in ANY


def test_lists():
    assert [1, 2, 3] not in Pattern([1, 2, 3, 4])
    assert [1, 2, 3, 4] not in Pattern([1, 2, 3])
    assert [2, 3, 1] not in Pattern([1, 2, 3])
    assert [1, 2, 3] in Pattern([1, ANY, 3])
    assert [1, 2, 3, 4] not in Pattern([1, ANY, 4])


def test_dicts():
    assert {'a': 1, 'b': 2} not in Pattern({'a': 1, 'b': 2, 'c': 3})
    assert {'a': 1, 'b': 2, 'c': 3} not in Pattern({'a': 1, 'b': 2})
    assert {'a': 1, 'b': 2} in Pattern({'a': ANY, 'b': 2})
    assert {'a': 1, 'b': 2} in Pattern(ANY.dict_with({'a': 1}))


def test_maybe():
    def nonzero(x):
        return x != 0

    pattern = Pattern(1).such_that(nonzero)
    assert 0 not in pattern
    assert 1 in pattern
    assert 2 not in pattern

    pattern = ANY.such_that(nonzero)
    assert 0 not in pattern
    assert 1 in pattern
    assert 2 in pattern


def test_success():
    assert {} in SUCCESS
    assert {} not in FAILURE


def test_failure():
    error = RequestFailure('error!')
    assert error not in SUCCESS
    assert error in FAILURE


class DataObject(object):
    def __init__(self, data):
        self.data = data

    def __data__(self):
        return self.data


def test_data():
    something = DataObject(('Something', {'a': 1}))
    assert something in Pattern(something.data)
    assert something not in Pattern(('Another', {'b': 2}))


def test_recursive():
    assert [
        False,
        True,
        DataObject(('Something', {'a': 1})),
        [1, 2, 3, {'aa': 4}],
        {
            'ba': [5, 6],
            'bb': [None],
            'bc': {},
            'bd': True,
            'be': [],
        }
    ] in Pattern([
            ANY,
            True,
            ('Something', {'a': 1}),
            [1, ANY, 3, {'aa': 4}],
            ANY.dict_with({
                'ba': ANY,
                'bb': [None],
                'bc': {},
            }),
    ])
