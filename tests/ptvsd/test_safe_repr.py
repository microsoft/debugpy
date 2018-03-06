import sys
import unittest

from ptvsd.safe_repr import SafeRepr, unicode, xrange


class SafeReprTests(unittest.TestCase):

    # TODO: Split up test_all().

    def test_all(self):
        saferepr = SafeRepr()

        # Test the string limiting somewhat automatically
        tests = []
        tests.append((7, 9, 'A' * (5)))
        tests.append((saferepr.maxstring_outer + 3, saferepr.maxstring_inner + 3 + 2, 'A' * (saferepr.maxstring_outer + 10)))  # noqa
        if sys.version_info >= (3, 0):
            tests.append((saferepr.maxstring_outer + 4, saferepr.maxstring_inner + 4 + 2, bytes('A', 'ascii') * (saferepr.maxstring_outer + 10)))  # noqa
        else:
            tests.append((saferepr.maxstring_outer + 4, saferepr.maxstring_inner + 4 + 2, unicode('A') * (saferepr.maxstring_outer + 10)))  # noqa

        for limit1, limit2, value in tests:
            assert len(saferepr(value)) <= limit1 <= len(repr(value)), (len(saferepr(value)), limit1, len(repr(value)), value)  # noqa
            assert len(saferepr([value])) <= limit2 <= len(repr([value])), (len(saferepr([value])), limit2, len(repr([value])), saferepr([value]))  # noqa

        def test(source, expected):
            actual = saferepr(source)
            if actual != expected:
                print("Source " + repr(source))
                print("Expect " + expected)
                print("Actual " + actual)
                print("")
                assert False

        def re_test(source, pattern):
            import re
            actual = saferepr(source)
            if not re.match(pattern, actual):
                print("Source  " + repr(source))
                print("Pattern " + pattern)
                print("Actual  " + actual)
                print("")
                assert False

        for ctype, _prefix, _suffix, comma in saferepr.collection_types:
            for i in range(len(saferepr.maxcollection)):
                prefix = _prefix * (i + 1)
                if comma:
                    suffix = _suffix + ("," + _suffix) * i
                else:
                    suffix = _suffix * (i + 1)
                #print("ctype = " + ctype.__name__ + ", maxcollection[" +
                #      str(i) + "] == " + str(saferepr.maxcollection[i]))
                c1 = ctype(range(saferepr.maxcollection[i] - 1))
                inner_repr = prefix + ', '.join(str(j) for j in c1)
                c2 = ctype(range(saferepr.maxcollection[i]))
                c3 = ctype(range(saferepr.maxcollection[i] + 1))
                for j in range(i):
                    c1, c2, c3 = ctype((c1,)), ctype((c2,)), ctype((c3,))
                test(c1, inner_repr + suffix)
                test(c2, inner_repr + ", ..." + suffix)
                test(c3, inner_repr + ", ..." + suffix)

                if ctype is set:
                    # Cannot recursively add sets to sets
                    break

        # Assume that all tests apply equally to all iterable types and only
        # test with lists.
        c1 = list(range(saferepr.maxcollection[0] * 2))
        c2 = [c1 for _ in range(saferepr.maxcollection[0] * 2)]
        c1_expect = '[' + ', '.join(str(j) for j in range(saferepr.maxcollection[0] - 1)) + ', ...]'  # noqa
        test(c1, c1_expect)
        c1_expect2 = '[' + ', '.join(str(j) for j in range(saferepr.maxcollection[1] - 1)) + ', ...]'  # noqa
        c2_expect = '[' + ', '.join(c1_expect2 for _ in range(saferepr.maxcollection[0] - 1)) + ', ...]'  # noqa
        test(c2, c2_expect)

        # Ensure dict keys and values are limited correctly
        d1 = {}
        d1_key = 'a' * saferepr.maxstring_inner * 2
        d1[d1_key] = d1_key
        re_test(d1, "{'a+\.\.\.a+': 'a+\.\.\.a+'}")
        d2 = {d1_key: d1}
        re_test(d2, "{'a+\.\.\.a+': {'a+\.\.\.a+': 'a+\.\.\.a+'}}")
        d3 = {d1_key: d2}
        if len(saferepr.maxcollection) == 2:
            re_test(d3, "{'a+\.\.\.a+': {'a+\.\.\.a+': {\.\.\.}}}")
        else:
            re_test(d3, "{'a+\.\.\.a+': {'a+\.\.\.a+': {'a+\.\.\.a+': 'a+\.\.\.a+'}}}")  # noqa

        # Ensure empty dicts work
        test({}, '{}')

        # Ensure dict keys are sorted
        d1 = {}
        d1['c'] = None
        d1['b'] = None
        d1['a'] = None
        test(d1, "{'a': None, 'b': None, 'c': None}")

        if sys.version_info >= (3, 0):
            # Ensure dicts with unsortable keys do not crash
            d1 = {}
            for _ in range(100):
                d1[object()] = None
            try:
                list(sorted(d1))
                assert False, "d1.keys() should be unorderable"
            except TypeError:
                pass
            saferepr(d1)

        # Test with objects with broken repr implementations
        class TestClass(object):
            def __repr__(saferepr):
                raise NameError
        try:
            repr(TestClass())
            assert False, "TestClass().__repr__ should have thrown"
        except NameError:
            pass
        saferepr(TestClass())

        # Test with objects with long repr implementations
        class TestClass(object):
            repr_str = '<' + 'A' * saferepr.maxother_outer * 2 + '>'

            def __repr__(saferepr):
                return saferepr.repr_str
        re_test(TestClass(), r'\<A+\.\.\.A+\>')

        # Test collections that don't override repr
        class TestClass(dict):
            pass
        test(TestClass(), '{}')

        class TestClass(list):
            pass
        test(TestClass(), '[]')

        # Test collections that override repr
        class TestClass(dict):
            def __repr__(saferepr):
                return 'MyRepr'
        test(TestClass(), 'MyRepr')

        class TestClass(list):
            def __init__(saferepr, iter=()):
                list.__init__(saferepr, iter)

            def __repr__(saferepr):
                return 'MyRepr'
        test(TestClass(), 'MyRepr')

        # Test collections and iterables with long repr
        test(TestClass(xrange(0, 15)), 'MyRepr')
        test(TestClass(xrange(0, 16)), '<TestClass, len() = 16>')
        test(TestClass([TestClass(xrange(0, 10))]), 'MyRepr')
        test(TestClass([TestClass(xrange(0, 11))]), '<TestClass, len() = 1>')

        # Test strings inside long iterables
        test(TestClass(['a' * (saferepr.maxcollection[1] + 1)]),
             'MyRepr')
        test(TestClass(['a' * (saferepr.maxstring_inner + 1)]),
             '<TestClass, len() = 1>')

        # Test range
        if sys.version[0] == '2':
            range_name = 'xrange'
        else:
            range_name = 'range'
        test(xrange(1, saferepr.maxcollection[0] + 1),
             '%s(1, %s)' % (range_name, saferepr.maxcollection[0] + 1))

        # Test directly recursive collections
        c1 = [1, 2]
        c1.append(c1)
        test(c1, '[1, 2, [...]]')
        d1 = {1: None}
        d1[2] = d1
        test(d1, '{1: None, 2: {...}}')

        # Find the largest possible repr and ensure it is below our arbitrary
        # limit (8KB).
        coll = '-' * (saferepr.maxstring_outer * 2)
        for limit in reversed(saferepr.maxcollection[1:]):
            coll = [coll] * (limit * 2)
        dcoll = {}
        for i in range(saferepr.maxcollection[0]):
            dcoll[str(i) * saferepr.maxstring_outer] = coll
        text = saferepr(dcoll)
        #try:
        #    text_repr = repr(dcoll)
        #except MemoryError:
        #    print('Memory error raised while creating repr of test data')
        #    text_repr = ''
        #print('len(SafeRepr()(dcoll)) = ' + str(len(text)) +
        #      ', len(repr(coll)) = ' + str(len(text_repr)))
        assert len(text) < 8192

        # Test numpy types - they should all use their native reprs,
        # even arrays exceeding limits
        try:
            import numpy as np
        except ImportError:
            msg = 'WARNING! could not import numpy - skipping all numpy tests.'
            print(msg)
        else:
            test(np.int32(123),
                 repr(np.int32(123)))
            test(np.float64(123.456),
                 repr(np.float64(123.456)))
            test(np.zeros(saferepr.maxcollection[0] + 1),
                 repr(np.zeros(saferepr.maxcollection[0] + 1)))
