import sys


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

    from _pydevd_bundle import pydevd_bytecode_utils
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


def test_get_smart_step_into_variant_from_frame_offset():
    from _pydevd_bundle import pydevd_bytecode_utils
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


def test_smart_step_into_bytecode_info_eq():

    from _pydevd_bundle import pydevd_bytecode_utils
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
