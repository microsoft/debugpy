from _pydevd_bundle.pydevd_extension_api import StrPresentationProvider
from .pydevd_helpers import find_mod_attr


class SizedShapeStr:
    '''Displays the size of an Sized object before displaying its value.
    '''
    def can_provide(self, type_object, type_name):
        sized_obj = find_mod_attr('collections.abc', 'Sized')
        return sized_obj is not None and issubclass(type_object, sized_obj)

    def get_str(self, val):
        if hasattr(val, 'shape'):
            return f'shape: {val.shape}, value: {val}'
        return f'len: {len(val)}, value: {val}'

import sys

if not sys.platform.startswith("java"):
    StrPresentationProvider.register(SizedShapeStr)
