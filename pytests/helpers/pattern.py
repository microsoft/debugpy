# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

from collections import defaultdict
import numbers

from ptvsd.compat import unicode


class BasePattern(object):
    def __repr__(self):
        raise NotImplementedError()

    def __contains__(self, data):
        raise NotImplementedError()

    def such_that(self, condition):
        return Maybe(self, condition)


class Pattern(BasePattern):
    """Represents a pattern of a data structure, that can be matched against the
    actual data by using operator "in".

    For lists and tuples, (data in pattern) is true if both are sequences of the
    same length, and for all valid I, (data[I] in Pattern(pattern[I])).

    For dicts, (data in pattern) is true if, for all K in data.keys() + pattern.keys(),
    data.has_key(K) and (data[K] in Pattern(pattern[K])). ANY.dict_with() can be used
    to perform partial matches.

    For any other type, (data in pattern) is true if pattern is ANY or data == pattern.

    If the match has failed, but data has a member called __data__,  then it is invoked
    without arguments, and the same match is performed against the returned value.
    This allows object to return a data value describing itself, that can then be matched
    by a corresponding data pattern. Typically, it's a tuple or a dict.

    See test_pattern.py for examples.
    """

    def __init__(self, pattern):
        self.pattern = pattern

    def __repr__(self):
        return repr(self.pattern)

    def _matches(self, data):
        import pytests.helpers.timeline as timeline
        pattern = self.pattern
        if isinstance(pattern, BasePattern):
            return data in pattern
        elif isinstance(data, tuple) and isinstance(pattern, tuple):
            return len(data) == len(pattern) and all(d in Pattern(p) for (p, d) in zip(pattern, data))
        elif isinstance(data, list) and isinstance(pattern, list):
            return tuple(data) in Pattern(tuple(pattern))
        elif isinstance(data, dict) and isinstance(pattern, dict):
            keys = set(tuple(data.keys()) + tuple(pattern.keys()))
            def pairs_match(key):
                try:
                    d = data[key]
                    p = pattern[key]
                except KeyError:
                    return False
                return d in Pattern(p)
            return all(pairs_match(key) for key in keys)
        elif isinstance(data, timeline.Occurrence) and isinstance(pattern, timeline.Expectation):
            return pattern.has_occurred_by(data)
        else:
            return data == pattern

    def __contains__(self, value):
        if self._matches(value):
            return True
        try:
            value.__data__
        except AttributeError:
            return False
        else:
            return value.__data__() in self


class Any(BasePattern):
    """Represents a wildcard in a pattern as used by json_matches(),
    and matches any single object in the same place in input data.
    """

    def __init__(self):
        pass

    def __repr__(self):
        return 'ANY'

    def __contains__(self, other):
        return True

    @staticmethod
    def dict_with(items):
        return AnyDictWith(items)


class AnyDictWith(BasePattern):
    """A pattern that matches any dict that contains the specified key-value pairs.

        d1 = {'a': 1, 'b': 2, 'c': 3}
        d2 = {'a': 1, 'b': 2}

        d1 in Pattern(d2)           # False (need exact match)
        d1 in ANY.dict_with(d2)     # True (subset matches)
    """

    def __init__(self, items=None):
        self.items = dict(items)
        self.pattern = Pattern(defaultdict(lambda: ANY, items))

    def __repr__(self):
        return repr(self.items)[:-1] + ', ...}'

    def __contains__(self, value):
        return value in self.pattern


class Maybe(BasePattern):
    """A pattern that matches if condition is True.
    """

    def __init__(self, pattern, condition):
        self.pattern = pattern
        self.condition = condition

    def __repr__(self):
        return 'Maybe(%r)' % self.pattern

    def __contains__(self, value):
        return self.condition(value) and value in self.pattern


class Success(BasePattern):
    """A pattern that matches a response body depending on whether the request succeeded or failed.
    """

    def __init__(self, success):
        self.success = success

    def __repr__(self):
        return 'SUCCESS' if self.success else 'FAILURE'

    def __contains__(self, response_body):
        return self.success != isinstance(response_body, Exception)


SUCCESS = Success(True)
FAILURE = Success(False)

ANY = Any()
ANY.bool = ANY.such_that(lambda x: x is True or x is False)
ANY.str = ANY.such_that(lambda x: isinstance(x, unicode))
ANY.num = ANY.such_that(lambda x: isinstance(x, numbers.Real))
ANY.int = ANY.such_that(lambda x: isinstance(x, numbers.Integral))
