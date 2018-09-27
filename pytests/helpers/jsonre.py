# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from collections import defaultdict


class Any(object):
    """Represents a wildcard in a pattern as used by json_matches(),
    and matches any single object in the same place in input data.
    """

    def __repr__(self):
        return '<*>'

    @staticmethod
    def dict_with(items):
        return Any.DictWith(items)

    class DictWith(defaultdict):
        """A dict subclass that returns ANY for any non-existent key.

        This can be used in conjunction with json_matches to match some keys
        in a dict while ignoring others. For example:

            d1 = {'a': 1, 'b': 2, 'c': 3}
            d2 = {'a': 1, 'b': 2}

            json_matches(d1, d2)                # False
            json_matches(d1, ANY.dict_with(d2)) # True
        """

        def __init__(self, other=None):
            super(Any.DictWith, self).__init__(lambda: ANY, other or {})

        def __repr__(self):
            return dict.__repr__(self)[:-2] + ', ...}'


ANY = Any()


def json_matches(data, pattern):
    """Match data against pattern, returning True if it matches, and False otherwise.

    The data argument must be an object obtained via json.load, or equivalent.
    In other words, it must be a recursive data structure consisting only of
    dicts, lists, strings, numbers, Booleans, and None.

    The pattern argument is like data, but can also use the special value ANY.

    For strings, numbers, Booleans and None, the data matches the pattern if they're
    equal as defined by ==, or if the pattern is ANY.

    For lists, the data matches the pattern if they're both of the same length,
    and if every element json_matches() the element in the other list with the same
    index.

    For dicts, the data matches the pattern if, for every K in data.keys() + pattern.keys(),
    data.has_key(K) and json_matches(data[K], pattern[K]). ANY.dict_with() can be used to
    perform partial matches.

    See test_jsonre.py for examples.
    """

    if isinstance(pattern, Any):
        return True
    elif isinstance(data, list):
        return len(data) == len(pattern) and all((json_matches(x, y) for x, y in zip(data, pattern)))
    elif isinstance(data, dict):
        keys = set(tuple(data.keys()) + tuple(pattern.keys()))
        def pairs_match(key):
            try:
                dval = data[key]
                pval = pattern[key]
            except KeyError:
                return False
            return json_matches(dval, pval)
        return all((pairs_match(key) for key in keys))
    else:
        return data == pattern
