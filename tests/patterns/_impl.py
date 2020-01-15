# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, division, print_function, unicode_literals

# The actual patterns are defined here, so that tests.patterns.some can redefine
# builtin names like str, int etc without affecting the implementations in this
# file - some.* then provides shorthand aliases.

import collections
import itertools
import py.path
import re
import sys

from debugpy.common import compat, fmt
from debugpy.common.compat import unicode, xrange
import pydevd_file_utils


class Some(object):
    """A pattern that can be tested against a value with == to see if it matches.
    """

    def matches(self, value):
        raise NotImplementedError

    def __repr__(self):
        try:
            return self.name
        except AttributeError:
            raise NotImplementedError

    def __eq__(self, value):
        return self.matches(value)

    def __ne__(self, value):
        return not self.matches(value)

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

    def equal_to(self, obj):
        return EqualTo(self, obj)

    def not_equal_to(self, obj):
        return NotEqualTo(self, obj)

    def same_as(self, obj):
        return SameAs(self, obj)

    def matching(self, regex, flags=0):
        """Same pattern, but it only matches if re.match(regex, flags) produces
        a match that corresponds to the entire string.
        """
        return Matching(self, regex, flags)

    # Used to obtain the JSON representation for logging. This is a hack, because
    # JSON serialization doesn't allow to customize raw output - this function can
    # only substitute for another object that is normally JSON-serializable. But
    # for patterns, we want <...> in the logs, not'"<...>". Thus, we insert dummy
    # marker chars here, such that it looks like "\002<...>\003" in serialized JSON -
    # and then tests.timeline._describe_message does a string substitution on the
    # result to strip out '"\002' and '\003"'.
    def __getstate__(self):
        return "\002" + repr(self) + "\003"


class Not(Some):
    """Matches the inverse of the pattern.
    """

    def __init__(self, pattern):
        self.pattern = pattern

    def __repr__(self):
        return fmt("~{0!r}", self.pattern)

    def matches(self, value):
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

    def matches(self, value):
        return any(pattern == value for pattern in self.patterns)

    def __or__(self, pattern):
        return Either(*(self.patterns + (pattern,)))


class Object(Some):
    """Matches anything.
    """

    name = "<?>"

    def matches(self, value):
        return True


class Thing(Some):
    """Matches anything that is not None.
    """

    name = "<>"

    def matches(self, value):
        return value is not None


class InstanceOf(Some):
    """Matches any object that is an instance of the specified type.
    """

    def __init__(self, classinfo, name=None):
        if isinstance(classinfo, type):
            classinfo = (classinfo,)
        assert len(classinfo) > 0 and all(
            (isinstance(cls, type) for cls in classinfo)
        ), "classinfo must be a type or a tuple of types"

        self.name = name
        self.classinfo = classinfo

    def __repr__(self):
        if self.name:
            name = self.name
        else:
            name = " | ".join(cls.__name__ for cls in self.classinfo)
        return fmt("<{0}>", name)

    def matches(self, value):
        return isinstance(value, self.classinfo)


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
        return fmt("path({0!r})", self.path)

    def __str__(self):
        return compat.filename_str(self.path)

    def __unicode__(self):
        return self.path

    def __getstate__(self):
        return self.path

    def matches(self, other):
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

    def __getstate__(self):
        items = ["\002...\003"]
        if not self.items:
            return items
        items *= 2
        items[1:1] = self.items
        return items

    def matches(self, other):
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
        self.items = collections.OrderedDict(items)

    def __repr__(self):
        return dict.__repr__(self.items)[:-1] + ", ...}"

    def __getstate__(self):
        items = self.items.copy()
        items["\002..."] = "...\003"
        return items

    def matches(self, other):
        if not isinstance(other, dict):
            return NotImplemented
        any = Object()
        d = {key: any for key in other}
        d.update(self.items)
        return d == other


class Also(Some):
    """Base class for patterns that narrow down another pattern.
    """

    def __init__(self, pattern):
        self.pattern = pattern

    def matches(self, value):
        return self.pattern == value and self._also(value)

    def _also(self, value):
        raise NotImplementedError


class SuchThat(Also):
    """Matches only if condition is true.
    """

    def __init__(self, pattern, condition):
        super(SuchThat, self).__init__(pattern)
        self.condition = condition

    def __repr__(self):
        try:
            return self.name
        except AttributeError:
            return fmt("({0!r} if {1})", self.pattern, compat.nameof(self.condition))

    def _also(self, value):
        return self.condition(value)


class InRange(Also):
    """Matches only if the value is within the specified range.
    """

    def __init__(self, pattern, start, stop):
        super(InRange, self).__init__(pattern)
        self.start = start
        self.stop = stop

    def __repr__(self):
        try:
            return self.name
        except AttributeError:
            return fmt("({0!r} <= {1!r} < {2!r})", self.start, self.pattern, self.stop)

    def _also(self, value):
        return self.start <= value < self.stop


class EqualTo(Also):
    """Matches any object that is equal to the specified object.
    """

    def __init__(self, pattern, obj):
        super(EqualTo, self).__init__(pattern)
        self.obj = obj

    def __repr__(self):
        return repr(self.obj)

    def __str__(self):
        return str(self.obj)

    def __unicode__(self):
        return unicode(self.obj)

    def __getstate__(self):
        return self.obj

    def _also(self, value):
        return self.obj == value


class NotEqualTo(Also):
    """Matches any object that is not equal to the specified object.
    """

    def __init__(self, pattern, obj):
        super(NotEqualTo, self).__init__(pattern)
        self.obj = obj

    def __repr__(self):
        return fmt("<!={0!r}>", self.obj)

    def _also(self, value):
        return self.obj != value


class SameAs(Also):
    """Matches one specific object only (i.e. makes '==' behave like 'is').
    """

    def __init__(self, pattern, obj):
        super(SameAs, self).__init__(pattern)
        self.obj = obj

    def __repr__(self):
        return fmt("<is {0!r}>", self.obj)

    def _also(self, value):
        return self.obj is value


class Matching(Also):
    """Matches any string that matches the specified regular expression.
    """

    def __init__(self, pattern, regex, flags=0):
        assert isinstance(regex, bytes) or isinstance(regex, unicode)
        super(Matching, self).__init__(pattern)
        self.regex = regex
        self.flags = flags

    def __repr__(self):
        s = repr(self.regex)
        if s[0] in "bu":
            return s[0] + "/" + s[2:-1] + "/"
        else:
            return "/" + s[1:-1] + "/"

    def _also(self, value):
        regex = self.regex

        # re.match() always starts matching at the beginning, but does not require
        # a complete match of the string - append "$" to ensure the latter.
        if isinstance(regex, bytes):
            if not isinstance(value, bytes):
                return NotImplemented
            regex += b"$"
        elif isinstance(regex, unicode):
            if not isinstance(value, unicode):
                return NotImplemented
            regex += "$"
        else:
            raise AssertionError()

        return re.match(regex, value, self.flags) is not None
