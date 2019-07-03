# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

"""Do not import this package directly - import tests.patterns.some instead.
"""

# The actual patterns are defined here, so that tests.patterns.some can redefine
# builtin names like str, int etc without affecting the implementations in this
# file - some.* then provides shorthand aliases.

import itertools
import py.path
import re
import sys

from ptvsd.common import compat, fmt
from ptvsd.common.compat import unicode, xrange
import pydevd_file_utils


class Some(object):
    """A pattern that can be tested against a value with == to see if it matches.
    """

    def __repr__(self):
        try:
            return self.name
        except AttributeError:
            raise NotImplementedError

    def __eq__(self, value):
        raise NotImplementedError

    def __ne__(self, other):
        return not (self == other)

    def __invert__(self):
        """The inverse pattern - matches everything that this one doesn't.
        """
        return Not(self)

    def __or__(self, pattern):
        """Union pattern - matches if either of the two patterns match.
        """
        return Either(self, pattern)

    def such_that(self, condition):
        """Same pattern, but it only matches if condition() is true.
        """
        return SuchThat(self, condition)

    def in_range(self, start, stop):
        """Same pattern, but it only matches if the start <= value < stop.
        """
        return InRange(self, start, stop)


class Not(Some):
    """Matches the inverse of the pattern.
    """

    def __init__(self, pattern):
        self.pattern = pattern

    def __repr__(self):
        return fmt("~{0!r}", self.pattern)

    def __eq__(self, value):
        return value != self.pattern


class Either(Some):
    """Matches either of the patterns.
    """

    def __init__(self, *patterns):
        assert len(patterns) > 0
        self.patterns = tuple(patterns)

    def __repr__(self):
        try:
            return self.name
        except AttributeError:
            return fmt("({0})", " | ".join(repr(pat) for pat in self.patterns))

    def __eq__(self, value):
        return any(pattern == value for pattern in self.patterns)

    def __or__(self, pattern):
        return Either(*(self.patterns + (pattern,)))


class SuchThat(Some):
    """Matches only if condition is true.
    """

    def __init__(self, pattern, condition):
        self.pattern = pattern
        self.condition = condition

    def __repr__(self):
        try:
            return self.name
        except AttributeError:
            return fmt("({0!r} if {1})", self.pattern, compat.nameof(self.condition))

    def __eq__(self, value):
        return self.condition(value) and value == self.pattern


class InRange(Some):
    """Matches only if the value is within the specified range.
    """

    def __init__(self, pattern, start, stop):
        self.pattern = pattern
        self.start = start
        self.stop = stop

    def __repr__(self):
        try:
            return self.name
        except AttributeError:
            return fmt("({0!r} <= {1!r} < {2!r})", self.start, self.pattern, self.stop)

    def __eq__(self, value):
        return self.start <= value < self.stop and value == self.pattern


class Object(Some):
    """Matches anything.
    """

    name = "<?>"

    def __eq__(self, value):
        return True

    def equal_to(self, obj):
        return EqualTo(obj)

    def same_as(self, obj):
        return SameAs(obj)


class Thing(Some):
    """Matches anything that is not None.
    """

    name = "<>"

    def __eq__(self, value):
        return value is not None


class InstanceOf(Some):
    """Matches any object that is an instance of the specified type.
    """

    def __init__(self, classinfo, name=None):
        if isinstance(classinfo, type):
            classinfo = (classinfo,)
        assert (
            len(classinfo) > 0 and
            all((isinstance(cls, type) for cls in classinfo))
        ), "classinfo must be a type or a tuple of types"

        self.name = name
        self.classinfo = classinfo

    def __repr__(self):
        if self.name:
            name = self.name
        else:
            name = " | ".join(cls.__name__ for cls in self.classinfo)
        return fmt("<{0}>", name)

    def __eq__(self, value):
        return isinstance(value, self.classinfo)


class EqualTo(Some):
    """Matches any object that is equal to the specified object.
    """

    def __init__(self, obj):
        self.obj = obj

    def __repr__(self):
        return repr(self.obj)

    def __eq__(self, value):
        return self.obj == value


class SameAs(Some):
    """Matches one specific object only (i.e. makes '==' behave like 'is').
    """

    def __init__(self, obj):
        self.obj = obj

    def __repr__(self):
        return fmt("is {0!r}", self.obj)

    def __eq__(self, value):
        return self.obj is value


class StrMatching(Some):
    """Matches any string that matches the specified regular expression.
    """

    def __init__(self, regex):
        self.regex = regex

    def __repr__(self):
        return fmt("/{0}/", self.regex)

    def __eq__(self, other):
        if not (isinstance(other, bytes) or isinstance(other, unicode)):
            return NotImplemented
        return re.match(self.regex, other) is not None


class Path(Some):
    """Matches any string that matches the specified path.

    Uses os.path.normcase() to normalize both strings before comparison.

    If one string is unicode, but the other one is not, both strings are normalized
    to unicode using sys.getfilesystemencoding().
    """

    def __init__(self, path):
        if isinstance(path, py.path.local):
            path = path.strpath
        if isinstance(path, bytes):
            path = path.encode(sys.getfilesystemencoding())
        assert isinstance(path, unicode)
        self.path = path

    def __repr__(self):
        return fmt("some.path({0!r})", self.path)

    def __eq__(self, other):
        if isinstance(other, py.path.local):
            other = other.strpath

        if isinstance(other, unicode):
            pass
        elif isinstance(other, bytes):
            other = other.encode(sys.getfilesystemencoding())
        else:
            return NotImplemented

        left = pydevd_file_utils.get_path_with_real_case(self.path)
        right = pydevd_file_utils.get_path_with_real_case(other)
        return left == right


class ListContaining(Some):
    """Matches any list that contains the specified subsequence of elements.
    """

    def __init__(self, *items):
        self.items = tuple(items)

    def __repr__(self):
        if not self.items:
            return "[...]"
        s = repr(list(self.items))
        return fmt("[..., {0}, ...]", s[1:-1])

    def __eq__(self, other):
        if not isinstance(other, list):
            return NotImplemented

        items = self.items
        if not items:
            return True  # every list contains an empty sequence
        if len(items) == 1:
            return self.items[0] in other

        # Zip the other list with itself, shifting by one every time, to produce
        # tuples of equal length with items - i.e. all potential subsequences. So,
        # given other=[1, 2, 3, 4, 5] and items=(2, 3, 4), we want to get a list
        # like [(1, 2, 3), (2, 3, 4), (3, 4, 5)] - and then search for items in it.
        iters = [itertools.islice(other, i, None) for i in xrange(0, len(items))]
        subseqs = compat.izip(*iters)
        return any(subseq == items for subseq in subseqs)


class DictContaining(Some):
    """Matches any dict that contains the specified key-value pairs::

        d1 = {'a': 1, 'b': 2, 'c': 3}
        d2 = {'a': 1, 'b': 2}
        assert d1 == some.dict.containing(d2)
        assert d2 != some.dict.containing(d1)
    """

    def __init__(self, items):
        self.items = dict(items)

    def __repr__(self):
        return repr(self.items)[:-1] + ', ...}'

    def __eq__(self, other):
        if not isinstance(other, dict):
            return NotImplemented
        any = Object()
        d = {key: any for key in other}
        d.update(self.items)
        return d == other
