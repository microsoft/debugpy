from tests_python.debug_constants import IS_PY2


def test_dict_resolver():
    from _pydevd_bundle.pydevd_resolver import DictResolver
    dict_resolver = DictResolver()
    dct = {(1, 2): 2, u'22': 22}
    contents_debug_adapter_protocol = dict_resolver.get_contents_debug_adapter_protocol(dct)
    if IS_PY2:
        assert contents_debug_adapter_protocol == [
            ('(1, 2)', 2, '[(1, 2)]'), (u"u'22'", 22, u"[u'22']"), ('__len__', 2, '.__len__()')]
    else:
        assert contents_debug_adapter_protocol == [
            ("'22'", 22, "['22']"), ('(1, 2)', 2, '[(1, 2)]'), ('__len__', 2, '.__len__()')]


def test_object_resolver_simple():
    from _pydevd_bundle.pydevd_resolver import DefaultResolver
    default_resolver = DefaultResolver()

    class MyObject(object):

        def __init__(self):
            self.a = 10
            self.b = 20

    obj = MyObject()
    dictionary = default_resolver.get_dictionary(obj)
    assert dictionary == {'a': 10, 'b': 20}

    contents_debug_adapter_protocol = default_resolver.get_contents_debug_adapter_protocol(obj)
    assert contents_debug_adapter_protocol == [('a', 10, '.a'), ('b', 20, '.b')]


def test_object_resolver_error():
    from _pydevd_bundle.pydevd_resolver import DefaultResolver
    default_resolver = DefaultResolver()

    class MyObject(object):

        def __init__(self):
            self.a = 10

        def __dir__(self):
            return ['a', 'b']

        def __getattribute__(self, attr_name):
            if attr_name == 'b':
                raise RuntimeError('unavailable')
            return object.__getattribute__(self, attr_name)

    obj = MyObject()
    dictionary = default_resolver.get_dictionary(obj)
    b_value = dictionary.pop('b')
    assert dictionary == {'a': 10}
    assert "raise RuntimeError('unavailable')" in b_value

    contents_debug_adapter_protocol = default_resolver.get_contents_debug_adapter_protocol(obj)
    b_value = contents_debug_adapter_protocol.pop(-1)
    assert contents_debug_adapter_protocol == [('a', 10, '.a')]
    assert b_value[0] == 'b'
    assert "raise RuntimeError('unavailable')" in b_value[1]
    assert b_value[2] == '.b'


def test_object_resolver__dict__non_strings():
    from _pydevd_bundle.pydevd_resolver import DefaultResolver
    default_resolver = DefaultResolver()

    class MyObject(object):

        def __init__(self):
            self.__dict__[(1, 2)] = (3, 4)

    obj = MyObject()
    dictionary = default_resolver.get_dictionary(obj)
    if IS_PY2:
        assert 'attribute name must be string' in dictionary.pop('(1, 2)')
        assert dictionary == {}
    else:
        assert dictionary == {'(1, 2)': (3, 4)}

    contents_debug_adapter_protocol = default_resolver.get_contents_debug_adapter_protocol(obj)
    if IS_PY2:
        assert len(contents_debug_adapter_protocol) == 1
        entry = contents_debug_adapter_protocol[0]
        assert entry[0] == '(1, 2)'
        assert 'attribute name must be string' in entry[1]
        assert entry[2] == '.(1, 2)'
    else:
        assert contents_debug_adapter_protocol == [('(1, 2)', (3, 4), '.__dict__[(1, 2)]')]


def test_django_forms_resolver():
    from _pydevd_bundle.pydevd_resolver import DjangoFormResolver
    django_form_resolver = DjangoFormResolver()

    class MyObject(object):

        def __init__(self):
            self.__dict__[(1, 2)] = (3, 4)
            self.__dict__['errors'] = 'foo'

    obj = MyObject()

    dictionary = django_form_resolver.get_dictionary(obj)
    if IS_PY2:
        assert 'attribute name must be string' in dictionary.pop('(1, 2)')
        assert dictionary == {'errors': None}
    else:
        assert dictionary == {'(1, 2)': (3, 4), 'errors': None}

    obj._errors = 'bar'
    dictionary = django_form_resolver.get_dictionary(obj)
    if IS_PY2:
        assert 'attribute name must be string' in dictionary.pop('(1, 2)')
        assert dictionary == {'errors': 'bar', '_errors': 'bar'}
    else:
        assert dictionary == {'(1, 2)': (3, 4), 'errors': 'bar', '_errors': 'bar'}


def test_tuple_resolver():
    from _pydevd_bundle.pydevd_resolver import TupleResolver
    tuple_resolver = TupleResolver()
    lst = tuple(range(11))
    contents_debug_adapter_protocol = tuple_resolver.get_contents_debug_adapter_protocol(lst)
    assert contents_debug_adapter_protocol == [
        ('00', 0, '[0]'),
        ('01', 1, '[1]'),
        ('02', 2, '[2]'),
        ('03', 3, '[3]'),
        ('04', 4, '[4]'),
        ('05', 5, '[5]'),
        ('06', 6, '[6]'),
        ('07', 7, '[7]'),
        ('08', 8, '[8]'),
        ('09', 9, '[9]'),
        ('10', 10, '[10]'),
        ('__len__', 11, '.__len__()')
    ]

    assert tuple_resolver.get_dictionary(lst) == {
        '00': 0,
        '01': 1,
        '02': 2,
        '03': 3,
        '04': 4,
        '05': 5,
        '06': 6,
        '07': 7,
        '08': 8,
        '09': 9,
        '10': 10,
        '__len__': 11
    }

    lst = tuple(range(10))
    contents_debug_adapter_protocol = tuple_resolver.get_contents_debug_adapter_protocol(lst)
    assert contents_debug_adapter_protocol == [
        ('0', 0, '[0]'),
        ('1', 1, '[1]'),
        ('2', 2, '[2]'),
        ('3', 3, '[3]'),
        ('4', 4, '[4]'),
        ('5', 5, '[5]'),
        ('6', 6, '[6]'),
        ('7', 7, '[7]'),
        ('8', 8, '[8]'),
        ('9', 9, '[9]'),
        ('__len__', 10, '.__len__()')
    ]

    assert tuple_resolver.get_dictionary(lst) == {
        '0': 0,
        '1': 1,
        '2': 2,
        '3': 3,
        '4': 4,
        '5': 5,
        '6': 6,
        '7': 7,
        '8': 8,
        '9': 9,
        '__len__': 10
    }

