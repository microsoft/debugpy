import sys
import unittest

try:
    import numpy as np
except ImportError:
    np = None

from ptvsd.safe_repr import SafeRepr


PY_VER = sys.version_info[0]
assert PY_VER <= 3  # Fix the code when Python 4 comes around.
PY3K = PY_VER == 3

if PY3K:
    unicode = str
    xrange = range


def py2_only(f):
    deco = unittest.skipIf(PY_VER != 2, 'py2-only')
    return deco(f)


def py3_only(f):
    deco = unittest.skipIf(PY_VER == 2, 'py3-only')
    return deco(f)


class TestBase(unittest.TestCase):

    def setUp(self):
        super(TestBase, self).setUp()
        self.saferepr = SafeRepr()

    def assert_saferepr(self, value, expected):
        safe = self.saferepr(value)

        self.assertEqual(safe, expected)
        return safe

    def assert_unchanged(self, value, expected):
        actual = repr(value)

        safe = self.assert_saferepr(value, expected)
        self.assertEqual(safe, actual)

    def assert_shortened(self, value, expected):
        actual = repr(value)

        safe = self.assert_saferepr(value, expected)
        self.assertNotEqual(safe, actual)

    def assert_saferepr_regex(self, value, expected):
        safe = self.saferepr(value)

        if PY_VER == 2:
            self.assertRegexpMatches(safe, expected)
        else:
            self.assertRegex(safe, expected)
        return safe

    def assert_unchanged_regex(self, value, expected):
        actual = repr(value)

        safe = self.assert_saferepr_regex(value, expected)
        self.assertEqual(safe, actual)

    def assert_shortened_regex(self, value, expected):
        actual = repr(value)

        safe = self.assert_saferepr_regex(value, expected)
        self.assertNotEqual(safe, actual)


class SafeReprTests(TestBase):

    # TODO: Split up test_all().

    def test_all(self):
        for ctype, _prefix, _suffix, comma in SafeRepr.collection_types:
            for i in range(len(SafeRepr.maxcollection)):
                prefix = _prefix * (i + 1)
                if comma:
                    suffix = _suffix + ("," + _suffix) * i
                else:
                    suffix = _suffix * (i + 1)
                #print("ctype = " + ctype.__name__ + ", maxcollection[" +
                #      str(i) + "] == " + str(SafeRepr.maxcollection[i]))
                c1 = ctype(range(SafeRepr.maxcollection[i] - 1))
                inner_repr = prefix + ', '.join(str(j) for j in c1)
                c2 = ctype(range(SafeRepr.maxcollection[i]))
                c3 = ctype(range(SafeRepr.maxcollection[i] + 1))
                for j in range(i):
                    c1, c2, c3 = ctype((c1,)), ctype((c2,)), ctype((c3,))
                self.assert_unchanged(c1, inner_repr + suffix)
                self.assert_shortened(c2, inner_repr + ", ..." + suffix)
                self.assert_shortened(c3, inner_repr + ", ..." + suffix)

                if ctype is set:
                    # Cannot recursively add sets to sets
                    break

        # Assume that all tests apply equally to all iterable types and only
        # test with lists.
        c1 = list(range(SafeRepr.maxcollection[0] * 2))
        c2 = [c1 for _ in range(SafeRepr.maxcollection[0] * 2)]
        c1_expect = '[' + ', '.join(str(j) for j in range(SafeRepr.maxcollection[0] - 1)) + ', ...]'  # noqa
        self.assert_shortened(c1, c1_expect)
        c1_expect2 = '[' + ', '.join(str(j) for j in range(SafeRepr.maxcollection[1] - 1)) + ', ...]'  # noqa
        c2_expect = '[' + ', '.join(c1_expect2 for _ in range(SafeRepr.maxcollection[0] - 1)) + ', ...]'  # noqa
        self.assert_shortened(c2, c2_expect)

        # Ensure dict keys and values are limited correctly
        d1 = {}
        d1_key = 'a' * SafeRepr.maxstring_inner * 2
        d1[d1_key] = d1_key
        self.assert_shortened_regex(d1, "{'a+\.\.\.a+': 'a+\.\.\.a+'}")
        d2 = {d1_key: d1}
        self.assert_shortened_regex(d2, "{'a+\.\.\.a+': {'a+\.\.\.a+': 'a+\.\.\.a+'}}")  # noqa
        d3 = {d1_key: d2}
        if len(SafeRepr.maxcollection) == 2:
            self.assert_shortened_regex(d3, "{'a+\.\.\.a+': {'a+\.\.\.a+': {\.\.\.}}}")  # noqa
        else:
            self.assert_shortened_regex(d3, "{'a+\.\.\.a+': {'a+\.\.\.a+': {'a+\.\.\.a+': 'a+\.\.\.a+'}}}")  # noqa

        # Ensure empty dicts work
        self.assert_unchanged({}, '{}')

        # Ensure dict keys are sorted
        d1 = {}
        d1['c'] = None
        d1['b'] = None
        d1['a'] = None
        self.assert_saferepr(d1, "{'a': None, 'b': None, 'c': None}")

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
            self.saferepr(d1)

        # Test with objects with broken repr implementations
        class TestClass(object):
            def __repr__(_):
                raise NameError
        with self.assertRaises(NameError):
            repr(TestClass())
        self.saferepr(TestClass())

        # Test with objects with long repr implementations
        class TestClass(object):
            repr_str = '<' + 'A' * SafeRepr.maxother_outer * 2 + '>'

            def __repr__(self):
                return self.repr_str
        self.assert_shortened_regex(TestClass(), r'\<A+\.\.\.A+\>')

        # Test collections that don't override repr
        class TestClass(dict):
            pass
        self.assert_unchanged(TestClass(), '{}')

        class TestClass(list):
            pass
        self.assert_unchanged(TestClass(), '[]')

        # Test collections that override repr
        class TestClass(dict):
            def __repr__(_):
                return 'MyRepr'
        self.assert_unchanged(TestClass(), 'MyRepr')

        class TestClass(list):
            def __init__(self, it=()):
                list.__init__(self, it)

            def __repr__(_):
                return 'MyRepr'
        self.assert_unchanged(TestClass(), 'MyRepr')

        # Test collections and iterables with long repr
        self.assert_unchanged(TestClass(xrange(0, 15)),
                              'MyRepr')
        self.assert_shortened(TestClass(xrange(0, 16)),
                              '<TestClass, len() = 16>')
        self.assert_unchanged(TestClass([TestClass(xrange(0, 10))]),
                              'MyRepr')
        self.assert_shortened(TestClass([TestClass(xrange(0, 11))]),
                              '<TestClass, len() = 1>')

        # Test strings inside long iterables
        self.assert_unchanged(
            TestClass(['a' * (SafeRepr.maxcollection[1] + 1)]),
            'MyRepr',
        )
        self.assert_shortened(
            TestClass(['a' * (SafeRepr.maxstring_inner + 1)]),
            '<TestClass, len() = 1>',
        )

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
