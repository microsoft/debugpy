# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from .jsonre import ANY, json_matches


def test_scalars():
    values = [None, True, False, 0, -1, -1.0, 1.23, 'abc', 'abcd']
    for x in values:
        assert json_matches(x, ANY)
        for y in values:
            assert json_matches(x, y) == (x == y)


def test_lists():
    assert json_matches([], [])

    assert json_matches(
        [1, 2, 3],
        ANY)

    assert json_matches(
        [1, 2, 3],
        [1, 2, 3])

    assert not json_matches(
        [1, 2, 3],
        [1, 2, 3, 4])

    assert not json_matches(
        [1, 2, 3],
        [1, 2, 3, 4])

    assert not json_matches(
        [1, 2, 3],
        [2, 3, 1])

    assert json_matches(
        [1, 2, 3],
        [1, ANY, 3])

    assert not json_matches(
        [1, 2, 3, 4],
        [1, ANY, 4])


def test_dicts():
    assert json_matches({}, {})

    assert json_matches(
        {'a': 1, 'b': 2},
        ANY)

    assert json_matches(
        {'a': 1, 'b': 2},
        {'b': 2, 'a': 1})

    assert not json_matches(
        {'a': 1, 'b': 2},
        {'a': 1, 'b': 2, 'c': 3})

    assert not json_matches(
        {'a': 1, 'b': 2, 'c': 3},
        {'a': 1, 'b': 2})

    assert json_matches(
        {'a': 1, 'b': 2},
        {'a': ANY, 'b': 2})

    assert json_matches(
        {'a': 1, 'b': 2},
        ANY.dict_with({'a': 1}))


def test_recursive():
    assert json_matches(
        [
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
        ],
        [
            ANY,
            True,
            [1, ANY, 3, {'aa': 4}],
            ANY.dict_with({
                'ba': ANY,
                'bb': [None],
                'bc': {},
            }),
        ])
