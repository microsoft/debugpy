from _pydevd_bundle.pydevd_constants import IS_PY36_OR_GREATER, GENERATED_LEN_ATTR_NAME


def check_len_entry(len_entry, first_2_params):
    assert len_entry[:2] == first_2_params
    assert callable(len_entry[2])
    assert len_entry[2]('check') == 'len(check)'


def test_dict_resolver():
    from _pydevd_bundle.pydevd_resolver import DictResolver
    dict_resolver = DictResolver()
    dct = {(1, 2): 2, u'22': 22}
    contents_debug_adapter_protocol = clear_contents_debug_adapter_protocol(dict_resolver.get_contents_debug_adapter_protocol(dct))
    len_entry = contents_debug_adapter_protocol.pop(-1)
    check_len_entry(len_entry, (GENERATED_LEN_ATTR_NAME, 2))
    if IS_PY36_OR_GREATER:
        assert contents_debug_adapter_protocol == [
            ('(1, 2)', 2, '[(1, 2)]'), ("'22'", 22, "['22']")]

    else:
        assert contents_debug_adapter_protocol == [
            ("'22'", 22, "['22']"), ('(1, 2)', 2, '[(1, 2)]')]


def test_dict_resolver_hex():
    from _pydevd_bundle.pydevd_resolver import DictResolver
    dict_resolver = DictResolver()
    dct = {(1, 10, 100): (10000, 100000, 100000)}
    contents_debug_adapter_protocol = clear_contents_debug_adapter_protocol(
        dict_resolver.get_contents_debug_adapter_protocol(dct, fmt={'hex': True}))
    len_entry = contents_debug_adapter_protocol.pop(-1)
    check_len_entry(len_entry, (GENERATED_LEN_ATTR_NAME, 1))
    assert contents_debug_adapter_protocol == [
        ('(0x1, 0xa, 0x64)', (10000, 100000, 100000), '[(1, 10, 100)]'), ]


def test_object_resolver_simple():
    from _pydevd_bundle.pydevd_resolver import DefaultResolver
    default_resolver = DefaultResolver()

    class MyObject(object):

        def __init__(self):
            self.a = 10
            self.b = 20

    obj = MyObject()
    dictionary = clear_contents_dictionary(default_resolver.get_dictionary(obj))
    assert dictionary == {'a': 10, 'b': 20}

    contents_debug_adapter_protocol = clear_contents_debug_adapter_protocol(default_resolver.get_contents_debug_adapter_protocol(obj))
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


def test_object_resolver_hasattr_error():
    from _pydevd_bundle.pydevd_resolver import DefaultResolver
    from _pydevd_bundle.pydevd_xml import get_type
    default_resolver = DefaultResolver()

    class MyObject(object):

        def __getattribute__(self, attr_name):
            raise RuntimeError()

    obj = MyObject()
    dictionary = default_resolver.get_dictionary(obj)
    assert dictionary == {}

    _type_object, type_name, _resolver = get_type(obj)
    assert type_name == 'MyObject'


def test_object_resolver__dict__non_strings():
    from _pydevd_bundle.pydevd_resolver import DefaultResolver
    default_resolver = DefaultResolver()

    class MyObject(object):

        def __init__(self):
            self.__dict__[(1, 2)] = (3, 4)

    obj = MyObject()
    dictionary = clear_contents_dictionary(default_resolver.get_dictionary(obj))
    assert dictionary == {'(1, 2)': (3, 4)}

    contents_debug_adapter_protocol = clear_contents_debug_adapter_protocol(
        default_resolver.get_contents_debug_adapter_protocol(obj))
    assert contents_debug_adapter_protocol == [('(1, 2)', (3, 4), '.__dict__[(1, 2)]')]


def test_django_forms_resolver():
    from _pydevd_bundle.pydevd_resolver import DjangoFormResolver
    django_form_resolver = DjangoFormResolver()

    class MyObject(object):

        def __init__(self):
            self.__dict__[(1, 2)] = (3, 4)
            self.__dict__['errors'] = 'foo'

    obj = MyObject()

    dictionary = clear_contents_dictionary(django_form_resolver.get_dictionary(obj))
    assert dictionary == {'(1, 2)': (3, 4), 'errors': None}

    obj._errors = 'bar'
    dictionary = clear_contents_dictionary(django_form_resolver.get_dictionary(obj))
    assert dictionary == {'(1, 2)': (3, 4), 'errors': 'bar', '_errors': 'bar'}


def clear_contents_debug_adapter_protocol(contents_debug_adapter_protocol):
    lst = []
    for x in contents_debug_adapter_protocol:
        if not x[0].startswith('__'):

            if '<built-in method' in str(x[1]) or '<method-wrapper' in str(x[1]) or '<bound method' in str(x[1]):
                continue

            lst.append(x)

    return lst


def clear_contents_dictionary(dictionary):
    dictionary = dictionary.copy()
    for key in list(dictionary):
        if key.startswith('__') or key in ('count', 'index'):
            del dictionary[key]
    return dictionary


def test_tuple_resolver():
    from _pydevd_bundle.pydevd_resolver import TupleResolver
    tuple_resolver = TupleResolver()
    fmt = {'hex': True}
    lst = tuple(range(11))
    contents_debug_adapter_protocol = clear_contents_debug_adapter_protocol(
        tuple_resolver.get_contents_debug_adapter_protocol(lst))
    len_entry = contents_debug_adapter_protocol.pop(-1)
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
    ]
    check_len_entry(len_entry, (GENERATED_LEN_ATTR_NAME, 11))

    assert clear_contents_dictionary(tuple_resolver.get_dictionary(lst)) == {
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
        GENERATED_LEN_ATTR_NAME: 11
    }

    lst = tuple(range(17))
    contents_debug_adapter_protocol = clear_contents_debug_adapter_protocol(
        tuple_resolver.get_contents_debug_adapter_protocol(lst, fmt=fmt))
    len_entry = contents_debug_adapter_protocol.pop(-1)
    assert contents_debug_adapter_protocol == [
        ('0x00', 0, '[0]'),
        ('0x01', 1, '[1]'),
        ('0x02', 2, '[2]'),
        ('0x03', 3, '[3]'),
        ('0x04', 4, '[4]'),
        ('0x05', 5, '[5]'),
        ('0x06', 6, '[6]'),
        ('0x07', 7, '[7]'),
        ('0x08', 8, '[8]'),
        ('0x09', 9, '[9]'),
        ('0x0a', 10, '[10]'),
        ('0x0b', 11, '[11]'),
        ('0x0c', 12, '[12]'),
        ('0x0d', 13, '[13]'),
        ('0x0e', 14, '[14]'),
        ('0x0f', 15, '[15]'),
        ('0x10', 16, '[16]'),
    ]
    check_len_entry(len_entry, (GENERATED_LEN_ATTR_NAME, 17))

    assert clear_contents_dictionary(tuple_resolver.get_dictionary(lst, fmt=fmt)) == {
        '0x00': 0,
        '0x01': 1,
        '0x02': 2,
        '0x03': 3,
        '0x04': 4,
        '0x05': 5,
        '0x06': 6,
        '0x07': 7,
        '0x08': 8,
        '0x09': 9,
        '0x0a': 10,
        '0x0b': 11,
        '0x0c': 12,
        '0x0d': 13,
        '0x0e': 14,
        '0x0f': 15,
        '0x10': 16,
        GENERATED_LEN_ATTR_NAME: 17
    }

    lst = tuple(range(10))
    contents_debug_adapter_protocol = clear_contents_debug_adapter_protocol(tuple_resolver.get_contents_debug_adapter_protocol(lst))
    len_entry = contents_debug_adapter_protocol.pop(-1)
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
    ]
    check_len_entry(len_entry, (GENERATED_LEN_ATTR_NAME, 10))

    assert clear_contents_dictionary(tuple_resolver.get_dictionary(lst)) == {
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
        GENERATED_LEN_ATTR_NAME: 10
    }

    contents_debug_adapter_protocol = clear_contents_debug_adapter_protocol(tuple_resolver.get_contents_debug_adapter_protocol(lst, fmt=fmt))
    len_entry = contents_debug_adapter_protocol.pop(-1)
    assert contents_debug_adapter_protocol == [
        ('0x0', 0, '[0]'),
        ('0x1', 1, '[1]'),
        ('0x2', 2, '[2]'),
        ('0x3', 3, '[3]'),
        ('0x4', 4, '[4]'),
        ('0x5', 5, '[5]'),
        ('0x6', 6, '[6]'),
        ('0x7', 7, '[7]'),
        ('0x8', 8, '[8]'),
        ('0x9', 9, '[9]'),
    ]
    check_len_entry(len_entry, (GENERATED_LEN_ATTR_NAME, 10))

    assert clear_contents_dictionary(tuple_resolver.get_dictionary(lst, fmt=fmt)) == {
        '0x0': 0,
        '0x1': 1,
        '0x2': 2,
        '0x3': 3,
        '0x4': 4,
        '0x5': 5,
        '0x6': 6,
        '0x7': 7,
        '0x8': 8,
        '0x9': 9,
        GENERATED_LEN_ATTR_NAME: 10
    }


def test_tuple_resolver_mixed():
    from _pydevd_bundle.pydevd_resolver import TupleResolver
    tuple_resolver = TupleResolver()

    class CustomTuple(tuple):
        pass

    my_tuple = CustomTuple([1, 2])
    my_tuple.some_value = 10
    contents_debug_adapter_protocol = clear_contents_debug_adapter_protocol(tuple_resolver.get_contents_debug_adapter_protocol(my_tuple))
    len_entry = contents_debug_adapter_protocol.pop(-1)
    check_len_entry(len_entry, (GENERATED_LEN_ATTR_NAME, 2))
    assert contents_debug_adapter_protocol == [
        ('some_value', 10, '.some_value'), ('0', 1, '[0]'), ('1', 2, '[1]'), ]
