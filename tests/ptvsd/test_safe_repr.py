import sys
import unittest

try:
    import numpy as np
except ImportError:
    np = None

from ptvsd.safe_repr import SafeRepr


if sys.version_info[0] > 2:
    unicode = str
    xrange = range


def py2_only(f):
    deco = unittest.skipIf(sys.version_info[0] != 2, 'py2-only')
    return deco(f)


def py3_only(f):
    assert sys.version_info[0] <= 3
    deco = unittest.skipIf(sys.version_info[0] != 3, 'py3-only')
    return deco(f)


class TestBase(unittest.TestCase):

    def setUp(self):
        super(TestBase, self).setUp()
        self.saferepr = SafeRepr()

    def assert_unchanged(self, value, expected):
        safe = self.saferepr(value)
        actual = repr(value)

        self.assertEqual(safe, expected)
        self.assertEqual(safe, actual)

    def assert_shortened(self, value, expected):
        safe = self.saferepr(value)
        actual = repr(value)

        self.assertEqual(safe, expected)
        self.assertNotEqual(safe, actual)


class SafeReprTests(TestBase):

    # TODO: Split up test_all().

    def test_all(self):
        saferepr = SafeRepr()

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

    def test_largest_repr(self):
        # Find the largest possible repr and ensure it is below our arbitrary
        # limit (8KB).
        coll = '-' * (SafeRepr.maxstring_outer * 2)
        for limit in reversed(SafeRepr.maxcollection[1:]):
            coll = [coll] * (limit * 2)
        dcoll = {}
        for i in range(SafeRepr.maxcollection[0]):
            dcoll[str(i) * SafeRepr.maxstring_outer] = coll
        text = self.saferepr(dcoll)
        #try:
        #    text_repr = repr(dcoll)
        #except MemoryError:
        #    print('Memory error raised while creating repr of test data')
        #    text_repr = ''
        #print('len(SafeRepr()(dcoll)) = ' + str(len(text)) +
        #      ', len(repr(coll)) = ' + str(len(text_repr)))

        self.assertLess(len(text), 8192)


class StringTests(TestBase):

    def test_str_small(self):
        value = 'A' * 5

        self.assert_unchanged(value, "'AAAAA'")
        self.assert_unchanged([value], "['AAAAA']")

    def test_str_large(self):
        value = 'A' * (SafeRepr.maxstring_outer + 10)

        self.assert_shortened(value,
                              "'" + 'A' * 43689 + "..." + 'A' * 21844 + "'")
        self.assert_shortened([value], "['AAAAAAAAAAAAAAAAAAA...AAAAAAAAA']")

    def test_str_largest_unchanged(self):
        value = 'A' * (SafeRepr.maxstring_outer - 2)

        self.assert_unchanged(value, "'" + 'A' * 65534 + "'")

    def test_str_smallest_changed(self):
        value = 'A' * (SafeRepr.maxstring_outer - 1)

        self.assert_shortened(value,
                              "'" + 'A' * 43689 + "..." + 'A' * 21844 + "'")

    def test_str_list_largest_unchanged(self):
        value = 'A' * (SafeRepr.maxstring_inner - 2)

        self.assert_unchanged([value], "['" + 'A' * 28 + "']")

    def test_str_list_smallest_changed(self):
        value = 'A' * (SafeRepr.maxstring_inner - 1)

        self.assert_shortened([value], "['AAAAAAAAAAAAAAAAAAA...AAAAAAAAA']")

    @py2_only
    def test_unicode_small(self):
        value = u'A' * 5

        self.assert_unchanged(value, "u'AAAAA'")
        self.assert_unchanged([value], "[u'AAAAA']")

    @py2_only
    def test_unicode_large(self):
        value = u'A' * (SafeRepr.maxstring_outer + 10)

        self.assert_shortened(value,
                              "u'" + 'A' * 43688 + "..." + 'A' * 21844 + "'")
        self.assert_shortened([value], "[u'AAAAAAAAAAAAAAAAAA...AAAAAAAAA']")

    @py3_only
    def test_bytes_small(self):
        value = b'A' * 5

        self.assert_unchanged(value, "b'AAAAA'")
        self.assert_unchanged([value], "[b'AAAAA']")

    @py3_only
    def test_bytes_large(self):
        value = b'A' * (SafeRepr.maxstring_outer + 10)

        self.assert_shortened(value,
                              "b'" + 'A' * 43688 + "..." + 'A' * 21844 + "'")
        self.assert_shortened([value], "[b'AAAAAAAAAAAAAAAAAA...AAAAAAAAA']")

    @unittest.skip('not written')  # TODO: finish!
    def test_bytearray_small(self):
        raise NotImplementedError

    @unittest.skip('not written')  # TODO: finish!
    def test_bytearray_large(self):
        raise NotImplementedError


class NumberTests(TestBase):

    @unittest.skip('not written')  # TODO: finish!
    def test_int(self):
        raise NotImplementedError

    @unittest.skip('not written')  # TODO: finish!
    def test_float(self):
        raise NotImplementedError

    @unittest.skip('not written')  # TODO: finish!
    def test_complex(self):
        raise NotImplementedError


class ContainerBase(object):

    @unittest.skip('not written')  # TODO: finish!
    def test_empty(self):
        raise NotImplementedError

    @unittest.skip('not written')  # TODO: finish!
    def test_subclass(self):
        raise NotImplementedError


class TupleTests(ContainerBase, TestBase):
    pass


class ListTests(ContainerBase, TestBase):

    def test_directly_recursive(self):
        value = [1, 2]
        value.append(value)

        self.assert_unchanged(value, '[1, 2, [...]]')

    def test_indirectly_recursive(self):
        value = [1, 2]
        value.append([value])

        self.assert_unchanged(value, '[1, 2, [[...]]]')


class FrozensetTests(ContainerBase, TestBase):
    pass


class SetTests(ContainerBase, TestBase):
    pass


class DictTests(ContainerBase, TestBase):

    def test_directly_recursive(self):
        value = {1: None}
        value[2] = value

        self.assert_unchanged(value, '{1: None, 2: {...}}')

    def test_indirectly_recursive(self):
        value = {1: None}
        value[2] = {3: value}

        self.assert_unchanged(value, '{1: None, 2: {3: {...}}}')


class OtherPythonTypeTests(TestBase):
    # not critical to test:
    #  singletons
    #  <function>
    #  <class>
    #  <iterator>
    #  memoryview
    #  classmethod
    #  staticmethod
    #  property
    #  enumerate
    #  reversed
    #  object
    #  type
    #  super

    @unittest.skip('not written')  # TODO: finish!
    def test_file(self):
        raise NotImplementedError

    def test_range_small(self):
        range_name = xrange.__name__
        value = xrange(1, 42)

        self.assert_unchanged(value, '{}(1, 42)'.format(range_name))

    @py3_only
    def test_range_large_stop_only(self):
        range_name = xrange.__name__
        stop = SafeRepr.maxcollection[0]
        value = xrange(stop)

        self.assert_unchanged(value,
                              '{}(0, {})'.format(range_name, stop))

    def test_range_large_with_start(self):
        range_name = xrange.__name__
        stop = SafeRepr.maxcollection[0] + 1
        value = xrange(1, stop)

        self.assert_unchanged(value,
                              '{}(1, {})'.format(range_name, stop))

    @unittest.skip('not written')  # TODO: finish!
    def test_named_struct(self):
        # e.g. sys.version_info
        raise NotImplementedError

    @unittest.skip('not written')  # TODO: finish!
    def test_namedtuple(self):
        raise NotImplementedError

    @unittest.skip('not written')  # TODO: finish!
    @py3_only
    def test_SimpleNamespace(self):
        raise NotImplementedError


class UserDefinedObjectTests(TestBase):

    @unittest.skip('not written')  # TODO: finish!
    def test_object(self):
        raise NotImplementedError


@unittest.skipIf(np is None, 'could not import numpy')
class NumpyTests(TestBase):
    # numpy types should all use their native reprs, even arrays
    # exceeding limits.

    def test_int32(self):
        value = np.int32(123)

        self.assert_unchanged(value, repr(value))

    def test_float32(self):
        value = np.float32(123.456)

        self.assert_unchanged(value, repr(value))

    def test_zeros(self):
        value = np.zeros(SafeRepr.maxcollection[0] + 1)

        self.assert_unchanged(value, repr(value))
