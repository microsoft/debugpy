# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

import numbers
import re

from ptvsd.common.compat import unicode
from tests.helpers.pathutils import compare_path


class BasePattern(object):

    def __repr__(self):
        raise NotImplementedError()

    def __eq__(self, value):
        raise NotImplementedError()

    def such_that(self, condition):
        return Maybe(self, condition)


class Any(BasePattern):
    """Represents a wildcard in a pattern as used by json_matches(),
    and matches any single object in the same place in input data.
    """

    def __init__(self):
        pass

    def __repr__(self):
        return 'ANY'

    def __eq__(self, other):
        return True

    @staticmethod
    def dict_with(items):
        """A pattern that matches any dict that contains the specified key-value pairs.

            d1 = {'a': 1, 'b': 2, 'c': 3}
            d2 = {'a': 1, 'b': 2}

            d1 == Pattern(d2)           # False (need exact match)
            d1 == ANY.dict_with(d2)     # True (subset matches)
        """

        class AnyDictWith(object):

            def __repr__(self):
                return repr(items)[:-1] + ', ...}'

            def __eq__(self, other):
                if not isinstance(other, dict):
                    return NotImplemented
                d = {key: ANY for key in other}
                d.update(items)
                return d == other

            def __ne__(self, other):
                return not (self == other)

        items = dict(items)
        return AnyDictWith()


class Maybe(BasePattern):
    """A pattern that matches if condition is True.
    """

    name = None

    def __init__(self, pattern, condition):
        self.pattern = pattern
        self.condition = condition

    def __repr__(self):
        return self.name or 'Maybe(%r)' % self.pattern

    def __eq__(self, value):
        return self.condition(value) and value == self.pattern


class Success(BasePattern):
    """A pattern that matches a response body depending on whether the request succeeded or failed.
    """

    def __init__(self, success):
        self.success = success

    def __repr__(self):
        return 'SUCCESS' if self.success else 'FAILURE'

    def __eq__(self, response_body):
        return self.success != isinstance(response_body, Exception)


class Is(BasePattern):
    """A pattern that matches a specific object only (i.e. uses operator 'is' rather than '==').
    """

    def __init__(self, obj):
        self.obj = obj

    def __repr__(self):
        return 'Is(%r)' % self.obj

    def __eq__(self, value):
        return self.obj is value


class Path(object):
    """A pattern that matches strings as path, using os.path.normcase before comparison,
    and sys.getfilesystemencoding() to compare Unicode and non-Unicode strings.
    """

    def __init__(self, s):
        self.s = s

    def __repr__(self):
        return 'Path(%r)' % (self.s,)

    def __eq__(self, other):
        if not (isinstance(other, bytes) or isinstance(other, unicode)):
            return NotImplemented
        return compare_path(self.s, other, show=False)

    def __ne__(self, other):
        return not (self == other)


class Regex(object):
    """A pattern that matches strings against regex, as if with re.match().
    """

    def __init__(self, regex):
        self.regex = regex

    def __repr__(self):
        return '/%s/' % (self.regex,)

    def __eq__(self, other):
        if not (isinstance(other, bytes) or isinstance(other, unicode)):
            return NotImplemented
        return re.match(self.regex, other)

    def __ne__(self, other):
        return not (self == other)


SUCCESS = Success(True)
FAILURE = Success(False)

ANY = Any()

ANY.bool = ANY.such_that(lambda x: x is True or x is False)
ANY.bool.name = 'ANY.bool'

ANY.str = ANY.such_that(lambda x: isinstance(x, unicode))
ANY.str.name = 'ANY.str'

ANY.num = ANY.such_that(lambda x: isinstance(x, numbers.Real))
ANY.num.name = 'ANY.num'

ANY.int = ANY.such_that(lambda x: isinstance(x, numbers.Integral))
ANY.int.name = 'ANY.int'

# Note: in practice it could be any int32, but as in those cases we expect the number to be
# incremented sequentially, this should be reasonable for tests.
ANY.dap_id = ANY.such_that(lambda x: isinstance(x, numbers.Integral) and 0 <= x < 10000)
ANY.dap_id.name = 'ANY.dap_id'
