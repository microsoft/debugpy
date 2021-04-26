import sys
try:
    from _pydevd_bundle import pydevd_bytecode_utils
except ImportError:
    pass
import pytest

pytestmark = pytest.mark.skipif(sys.version_info[0] < 3, reason='Only available for Python 3.')


@pytest.fixture(autouse=True, scope='function')
def enable_strict():
    # In tests enable strict mode (in regular operation it'll be False and will just ignore
    # bytecodes we still don't handle as if it didn't change the stack).
    pydevd_bytecode_utils.STRICT_MODE = True
    yield
    pydevd_bytecode_utils.STRICT_MODE = False


def check(found, expected):
    assert len(found) == len(expected), '%s != %s' % (found, expected)

    last_offset = -1
    for f, e in zip(found, expected):
        if isinstance(e.name, (list, tuple, set)):
            assert f.name in e.name
        else:
            assert f.name == e.name
        assert f.is_visited == e.is_visited
        assert f.line == e.line
        assert f.call_order == e.call_order

        # We can't check the offset because it may be different among different python versions
        # so, just check that it's always in order.
        assert f.offset > last_offset
        last_offset = f.offset


def test_smart_step_into_bytecode_info():
    from _pydevd_bundle.pydevd_bytecode_utils import Variant

    def function():

        def some(arg):
            pass

        def call(arg):
            pass

        yield sys._getframe()
        call(some(call(some())))

    generator = iter(function())
    frame = next(generator)

    found = pydevd_bytecode_utils.calculate_smart_step_into_variants(
        frame, 0, 99999, base=function.__code__.co_firstlineno)

    check(found, [
        Variant(name=('_getframe', 'sys'), is_visited=True, line=8, offset=20, call_order=1),
        Variant(name='some', is_visited=False, line=9, offset=34, call_order=1),
        Variant(name='call', is_visited=False, line=9, offset=36, call_order=1),
        Variant(name='some', is_visited=False, line=9, offset=38, call_order=2),
        Variant(name='call', is_visited=False, line=9, offset=40, call_order=2),
    ])


def check_name_and_line(found, expected):
    names_and_lines = set()
    for variant in found:
        if variant.children_variants:
            for v in variant.children_variants:
                names_and_lines.add((v.name + (' (in %s)' % variant.name), v.line))
        else:
            names_and_lines.add((variant.name, variant.line))

    if names_and_lines != set(expected):
        raise AssertionError('Found: %s' % (sorted(names_and_lines, key=lambda tup:tuple(reversed(tup))),))


def test_smart_step_into_bytecode_info_002():

    def function():
        yield sys._getframe()
        completions = foo.bar(
            Something(param1, param2=xxx.yyy),
        )
        call()

    generator = iter(function())
    frame = next(generator)

    found = pydevd_bytecode_utils.calculate_smart_step_into_variants(
        frame, 0, 99999, base=function.__code__.co_firstlineno)

    check_name_and_line(found, [('_getframe', 1), ('bar', 2), ('Something', 3), ('yyy', 3), ('call', 5)])


def test_smart_step_into_bytecode_info_003():

    def function():
        yield sys._getframe()
        bbb = foo.bar(
            Something(param1, param2=xxx.yyy), {}
        )
        call()

    generator = iter(function())
    frame = next(generator)

    found = pydevd_bytecode_utils.calculate_smart_step_into_variants(
        frame, 0, 99999, base=function.__code__.co_firstlineno)

    check_name_and_line(found, [('_getframe', 1), ('bar', 2), ('Something', 3), ('yyy', 3), ('call', 5)])


def test_smart_step_into_bytecode_info_004():

    def function():
        yield sys._getframe()
        bbb = foo.bar(
            Something(param1, param2=xxx.yyy), {1: 1}  # BUILD_MAP
        )
        call()

    generator = iter(function())
    frame = next(generator)

    found = pydevd_bytecode_utils.calculate_smart_step_into_variants(
        frame, 0, 99999, base=function.__code__.co_firstlineno)

    check_name_and_line(found, [('_getframe', 1), ('bar', 2), ('Something', 3), ('yyy', 3), ('call', 5)])


def test_smart_step_into_bytecode_info_005():

    def function():
        yield sys._getframe()
        bbb = foo.bar(
            Something(param1, param2=xxx.yyy), {1: 1, 2:2}  # BUILD_CONST_KEY_MAP
        )
        call()

    generator = iter(function())
    frame = next(generator)

    found = pydevd_bytecode_utils.calculate_smart_step_into_variants(
        frame, 0, 99999, base=function.__code__.co_firstlineno)

    check_name_and_line(found, [
        ('_getframe', 1), ('bar', 2), ('Something', 3), ('yyy', 3), ('call', 5)])


def test_smart_step_into_bytecode_info_006():

    def function():
        yield sys._getframe()
        foo.bar(
            Something(),
            {
                1: 1,
                2:[
                    x for x
                    in call()
                ]
            }
        )
        call2()

    generator = iter(function())
    frame = next(generator)

    found = pydevd_bytecode_utils.calculate_smart_step_into_variants(
        frame, 0, 99999, base=function.__code__.co_firstlineno)

    check_name_and_line(found, [
        ('_getframe', 1), ('bar', 2), ('Something', 3), ('call', 8), ('call2', 12)])


def test_smart_step_into_bytecode_info_007():

    def function():
        yield sys._getframe()
        a[0]

    generator = iter(function())
    frame = next(generator)

    found = pydevd_bytecode_utils.calculate_smart_step_into_variants(
        frame, 0, 99999, base=function.__code__.co_firstlineno)

    check_name_and_line(found, [('_getframe', 1), ('__getitem__', 2)])


def test_smart_step_into_bytecode_info_008():

    def function():
        yield sys._getframe()
        call(
            [1, 2, 3])

    generator = iter(function())
    frame = next(generator)

    found = pydevd_bytecode_utils.calculate_smart_step_into_variants(
        frame, 0, 99999, base=function.__code__.co_firstlineno)

    check_name_and_line(found, [('_getframe', 1), ('call', 2)])


def test_smart_step_into_bytecode_info_009():

    def function():
        yield sys._getframe()
        [1, 2, 3][0]()

    generator = iter(function())
    frame = next(generator)

    found = pydevd_bytecode_utils.calculate_smart_step_into_variants(
        frame, 0, 99999, base=function.__code__.co_firstlineno)

    check_name_and_line(found, [('_getframe', 1), ('__getitem__', 2), ('__getitem__().__call__', 2)])


def test_smart_step_into_bytecode_info_011():

    def function():
        yield sys._getframe()
        [1, 2, 3][0]()()

    generator = iter(function())
    frame = next(generator)

    found = pydevd_bytecode_utils.calculate_smart_step_into_variants(
        frame, 0, 99999, base=function.__code__.co_firstlineno)

    check_name_and_line(found, [('_getframe', 1), ('__getitem__', 2), ('__getitem__().__call__', 2), ('__call__().__call__', 2)])


def test_smart_step_into_bytecode_info_012():

    def function():
        yield sys._getframe()
        (lambda a:a)(1)

    generator = iter(function())
    frame = next(generator)

    found = pydevd_bytecode_utils.calculate_smart_step_into_variants(
        frame, 0, 99999, base=function.__code__.co_firstlineno)

    check_name_and_line(found, [('_getframe', 1), ('<lambda>', 2)])


def test_smart_step_into_bytecode_info_013():

    def function():
        yield sys._getframe()
        (lambda a:a,)[0](1)

    generator = iter(function())
    frame = next(generator)

    found = pydevd_bytecode_utils.calculate_smart_step_into_variants(
        frame, 0, 99999, base=function.__code__.co_firstlineno)

    check_name_and_line(found, [('_getframe', 1), ('__getitem__().__call__', 2), ('__getitem__', 2)])


def test_smart_step_into_bytecode_info_014():

    def function():
        yield sys._getframe()
        try:
            raise RuntimeError()
        except Exception:
            call2()
        finally:
            call3()

    generator = iter(function())
    frame = next(generator)

    found = pydevd_bytecode_utils.calculate_smart_step_into_variants(
        frame, 0, 99999, base=function.__code__.co_firstlineno)

    check_name_and_line(found, [('_getframe', 1), ('RuntimeError', 3), ('call2', 5), ('call3', 7)])


def test_smart_step_into_bytecode_info_015():

    def function():
        yield sys._getframe()
        with call():
            call2()

    generator = iter(function())
    frame = next(generator)

    found = pydevd_bytecode_utils.calculate_smart_step_into_variants(
        frame, 0, 99999, base=function.__code__.co_firstlineno)

    check_name_and_line(found, [('_getframe', 1), ('call', 2), ('call2', 3)])


def test_smart_step_into_bytecode_info_016():

    def function():
        yield sys._getframe()
        call2(
            1,
            2,
            a=3,
            *args,
            **kwargs
        )

    generator = iter(function())
    frame = next(generator)

    found = pydevd_bytecode_utils.calculate_smart_step_into_variants(
        frame, 0, 99999, base=function.__code__.co_firstlineno)

    check_name_and_line(found, [('_getframe', 1), ('call2', 2)])


def test_smart_step_into_bytecode_info_017():

    def function():
        yield sys._getframe()
        call([
            x for x in y
            if x == call2()
        ])

    generator = iter(function())
    frame = next(generator)

    found = pydevd_bytecode_utils.calculate_smart_step_into_variants(
        frame, 0, 99999, base=function.__code__.co_firstlineno)

    check_name_and_line(found,
        [('_getframe', 1), ('call', 2), ('__eq__ (in <listcomp>)', 4), ('call2 (in <listcomp>)', 4)]
    )


def test_smart_step_into_bytecode_info_018():

    def function():
        yield sys._getframe()

        class Foo(object):

            def __init__(self):
                pass

        f = Foo()

    generator = iter(function())
    frame = next(generator)

    found = pydevd_bytecode_utils.calculate_smart_step_into_variants(
        frame, 0, 99999, base=function.__code__.co_firstlineno)

    check_name_and_line(found, [('_getframe', 1), ('Foo', 8)])


def test_smart_step_into_bytecode_info_019():

    def function():
        yield sys._getframe()

        class Foo(object):

            def __init__(self):
                pass

        f = Foo()

    generator = iter(function())
    frame = next(generator)

    found = pydevd_bytecode_utils.calculate_smart_step_into_variants(
        frame, 0, 99999, base=function.__code__.co_firstlineno)

    check_name_and_line(found, [('_getframe', 1), ('Foo', 8)])


def test_smart_step_into_bytecode_info_020():

    def function():
        yield sys._getframe()
        for a in call():
            if a != 1:
                a()
                break
            elif a != 2:
                b()
                break
            else:
                continue
        else:
            raise RuntimeError()

    generator = iter(function())
    frame = next(generator)

    found = pydevd_bytecode_utils.calculate_smart_step_into_variants(
        frame, 0, 99999, base=function.__code__.co_firstlineno)

    check_name_and_line(found, [
        ('_getframe', 1), ('call', 2), ('__ne__', 3), ('a', 4), ('__ne__', 6), ('b', 7), ('RuntimeError', 12)])


def test_smart_step_into_bytecode_info_021():

    def function():
        yield sys._getframe()
        a, b = b, a
        a, b, c = c, a, b
        a, b, c, d = d, c, a, b
        a()

    generator = iter(function())
    frame = next(generator)

    found = pydevd_bytecode_utils.calculate_smart_step_into_variants(
        frame, 0, 99999, base=function.__code__.co_firstlineno)

    check_name_and_line(found, [('_getframe', 1), ('a', 5)])


def test_smart_step_into_bytecode_info_022():

    def function():
        yield sys._getframe()
        a(
            *{1, 2},
            **{
                1:('1' + '2'),
                2: tuple(
                    x for x in c()
                    if x == d())
            }
        )
        b()

    generator = iter(function())
    frame = next(generator)

    found = pydevd_bytecode_utils.calculate_smart_step_into_variants(
        frame, 0, 99999, base=function.__code__.co_firstlineno)

    check_name_and_line(found, [
        ('_getframe', 1), ('a', 2), ('tuple', 6), ('c', 7), ('__eq__ (in <genexpr>)', 8), ('d (in <genexpr>)', 8), ('b', 11)])


def test_smart_step_into_bytecode_info_023():

    def function():
        yield sys._getframe()
        tuple(
            x for x in
             c()
             if x == d()
        )
        tuple(
            x for x in
             c()
             if x == d()
        )

    generator = iter(function())
    frame = next(generator)

    found = pydevd_bytecode_utils.calculate_smart_step_into_variants(
        frame, 0, 99999, base=function.__code__.co_firstlineno)

    check_name_and_line(found, [
        ('_getframe', 1), ('tuple', 2), ('c', 4), ('__eq__ (in <genexpr>)', 5), ('d (in <genexpr>)', 5), ('tuple', 7), ('c', 9), ('__eq__ (in <genexpr>)', 10), ('d (in <genexpr>)', 10)])


def test_smart_step_into_bytecode_info_024():

    func = '''def function():
        yield sys._getframe()
        call(a ** b)
        call(a * b)
        call(a @ b)
        call(a / b)
        call(a // b)
        call(a % b)
        call(a + b)
        call(a - b)
        call(a >> b)
        call(a << b)
        call(a & b)
        call(a | b)
        call(a ^ b)
'''
    locs = {}
    exec(func, globals(), locs)

    function = locs['function']

    generator = iter(function())
    frame = next(generator)

    found = pydevd_bytecode_utils.calculate_smart_step_into_variants(
        frame, 0, 99999, base=function.__code__.co_firstlineno)

    check_name_and_line(found, [
        ('_getframe', 1),
        ('__pow__', 2),
        ('call', 2),

        ('__mul__', 3),
        ('call', 3),

        ('__matmul__', 4),
        ('call', 4),

        ('__div__', 5),
        ('call', 5),

        ('__floordiv__', 6),
        ('call', 6),

        ('__mod__', 7),
        ('call', 7),

        ('__add__', 8),
        ('call', 8),

        ('__sub__', 9),
        ('call', 9),

        ('__rshift__', 10),
        ('call', 10),

        ('__lshift__', 11),
        ('call', 11),

        ('__and__', 12),
        ('call', 12),

        ('__or__', 13),
        ('call', 13),

        ('__xor__', 14),
        ('call', 14)],
    )


def test_smart_step_into_bytecode_info_025():

    func = '''def function():
        yield sys._getframe()
        a **= b
        a *= b
        a @= b
        a /= b
        a //= b
        a %= b
        a += b
        a -= b
        a >>= b
        a <<= b
        a &= b
        a |= b
        a ^= b
        call()
'''
    locs = {}
    exec(func, globals(), locs)

    function = locs['function']

    generator = iter(function())
    frame = next(generator)

    found = pydevd_bytecode_utils.calculate_smart_step_into_variants(
        frame, 0, 99999, base=function.__code__.co_firstlineno)

    check_name_and_line(found, [('_getframe', 1), ('call', 15)])


@pytest.mark.skipif(sys.version_info[0:2] < (3, 8), reason='Walrus operator only available for Python 3.8 onwards.')
def test_smart_step_into_bytecode_info_026():

    func = '''def function():
    yield sys._getframe()
    call((a:=1))
'''
    locs = {}
    exec(func, globals(), locs)

    function = locs['function']
    generator = iter(function())
    frame = next(generator)

    found = pydevd_bytecode_utils.calculate_smart_step_into_variants(
        frame, 0, 99999, base=function.__code__.co_firstlineno)

    check_name_and_line(found, [('_getframe', 1), ('call', 2)])


def test_smart_step_into_bytecode_info_027():

    def function():
        yield sys._getframe()

        def call():
            pass

        a = [1, call]
        a[:1] = []
        x = a[0]()

    generator = iter(function())
    frame = next(generator)

    found = pydevd_bytecode_utils.calculate_smart_step_into_variants(
        frame, 0, 99999, base=function.__code__.co_firstlineno)

    check_name_and_line(found, [('_getframe', 1), ('__getitem__', 8), ('__getitem__().__call__', 8)])


def test_smart_step_into_bytecode_info_028():

    def function():
        yield sys._getframe()

        def call():
            pass

        a = [1, call]
        a[:1] += []
        x = a[0]()

    generator = iter(function())
    frame = next(generator)

    found = pydevd_bytecode_utils.calculate_smart_step_into_variants(
        frame, 0, 99999, base=function.__code__.co_firstlineno)

    check_name_and_line(found, [('_getframe', 1), ('__getitem__', 7), ('__getitem__', 8), ('__getitem__().__call__', 8)])


def test_smart_step_into_bytecode_info_029():

    def function():
        yield sys._getframe()

        call((+b) + (-b) - (not b) * (~b))

    generator = iter(function())
    frame = next(generator)

    found = pydevd_bytecode_utils.calculate_smart_step_into_variants(
        frame, 0, 99999, base=function.__code__.co_firstlineno)

    check_name_and_line(found, [('_getframe', 1), ('__add__', 3), ('__mul__', 3), ('__sub__', 3), ('call', 3)])


def test_smart_step_into_bytecode_info_030():

    def function():
        yield sys._getframe()

        call({a for a in b})

    generator = iter(function())
    frame = next(generator)

    found = pydevd_bytecode_utils.calculate_smart_step_into_variants(
        frame, 0, 99999, base=function.__code__.co_firstlineno)

    check_name_and_line(found, [('_getframe', 1), ('call', 3)])


def test_smart_step_into_bytecode_info_031():

    def function():
        yield sys._getframe()

        call({a: b for a in b})

    generator = iter(function())
    frame = next(generator)

    found = pydevd_bytecode_utils.calculate_smart_step_into_variants(
        frame, 0, 99999, base=function.__code__.co_firstlineno)

    check_name_and_line(found, [('_getframe', 1), ('call', 3)])


def test_smart_step_into_bytecode_info_032():

    def function():
        yield sys._getframe()

        del a[:2]
        call()

    generator = iter(function())
    frame = next(generator)

    found = pydevd_bytecode_utils.calculate_smart_step_into_variants(
        frame, 0, 99999, base=function.__code__.co_firstlineno)

    check_name_and_line(found, [('_getframe', 1), ('call', 4)])


def test_smart_step_into_bytecode_info_033():

    def function():
        yield sys._getframe()

        raise call()

    generator = iter(function())
    frame = next(generator)

    found = pydevd_bytecode_utils.calculate_smart_step_into_variants(
        frame, 0, 99999, base=function.__code__.co_firstlineno)

    check_name_and_line(found, [('_getframe', 1), ('call', 3)])


def test_get_smart_step_into_variant_from_frame_offset():
    from _pydevd_bundle.pydevd_bytecode_utils import Variant

    found = [
        Variant(name='_getframe', is_visited=True, line=8, offset=20, call_order=1),
        Variant(name='some', is_visited=False, line=9, offset=34, call_order=1),
        Variant(name='call', is_visited=False, line=9, offset=36, call_order=1),
        Variant(name='some', is_visited=False, line=9, offset=38, call_order=2),
        Variant(name='call', is_visited=False, line=9, offset=40, call_order=2),
    ]
    assert pydevd_bytecode_utils.get_smart_step_into_variant_from_frame_offset(19, found) is None
    assert pydevd_bytecode_utils.get_smart_step_into_variant_from_frame_offset(20, found).offset == 20

    assert pydevd_bytecode_utils.get_smart_step_into_variant_from_frame_offset(33, found).offset == 20

    assert pydevd_bytecode_utils.get_smart_step_into_variant_from_frame_offset(34, found).offset == 34
    assert pydevd_bytecode_utils.get_smart_step_into_variant_from_frame_offset(35, found).offset == 34

    assert pydevd_bytecode_utils.get_smart_step_into_variant_from_frame_offset(36, found).offset == 36

    assert pydevd_bytecode_utils.get_smart_step_into_variant_from_frame_offset(44, found).offset == 40


def test_smart_step_into_bytecode_info_00eq():
    from _pydevd_bundle.pydevd_bytecode_utils import Variant

    def function():
        a = 1
        b = 1
        if a == b:
            pass
        if a != b:
            pass
        if a > b:
            pass
        if a >= b:
            pass
        if a < b:
            pass
        if a <= b:
            pass
        if a is b:
            pass

        yield sys._getframe()

    generator = iter(function())
    frame = next(generator)

    found = pydevd_bytecode_utils.calculate_smart_step_into_variants(
        frame, 0, 99999, base=function.__code__.co_firstlineno)

    if sys.version_info[:2] < (3, 9):
        check(found, [
            Variant(name='__eq__', is_visited=True, line=3, offset=18, call_order=1),
            Variant(name='__ne__', is_visited=True, line=5, offset=33, call_order=1),
            Variant(name='__gt__', is_visited=True, line=7, offset=48, call_order=1),
            Variant(name='__ge__', is_visited=True, line=9, offset=63, call_order=1),
            Variant(name='__lt__', is_visited=True, line=11, offset=78, call_order=1),
            Variant(name='__le__', is_visited=True, line=13, offset=93, call_order=1),
            Variant(name='is', is_visited=True, line=15, offset=108, call_order=1),
            Variant(name=('_getframe', 'sys'), is_visited=True, line=18, offset=123, call_order=1),
        ])
    else:
        check(found, [
            Variant(name='__eq__', is_visited=True, line=3, offset=18, call_order=1),
            Variant(name='__ne__', is_visited=True, line=5, offset=33, call_order=1),
            Variant(name='__gt__', is_visited=True, line=7, offset=48, call_order=1),
            Variant(name='__ge__', is_visited=True, line=9, offset=63, call_order=1),
            Variant(name='__lt__', is_visited=True, line=11, offset=78, call_order=1),
            Variant(name='__le__', is_visited=True, line=13, offset=93, call_order=1),
            Variant(name=('_getframe', 'sys'), is_visited=True, line=18, offset=123, call_order=1),
        ])
