# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

"""When imported using from, this module effectively overrides the print() built-in
with a synchronized version that also adds a timestamp.

Because tests can run in parallel, all modules that can be invoked from test code,
and that need to print, should do::

    from tests import print

Each call to print() is then atomic - i.e. it will not interleave with any other print.
If a sequence of several print calls must be atomic, lock explicitly::

    with print:
        print('fizz')
        print('bazz')
"""

import sys
import types

from ptvsd.common import fmt, singleton, timestamp


# The class of the module object for this module.
class Printer(singleton.ThreadSafeSingleton, types.ModuleType):
    def __init__(self):
        # Set self up as a proper module, and copy globals.
        # types must be re-imported, because globals aren't there yet at this point.
        import types
        types.ModuleType.__init__(self, __name__)
        self.__dict__.update(sys.modules[__name__].__dict__)

    @singleton.autolocked_method
    def __call__(self, *args, **kwargs):
        """Like builtin print(), but synchronized across multiple threads,
        and adds a timestamp.
        """
        with self:
            timestamped = kwargs.pop('timestamped', True)
            t = timestamp.current() if timestamped else None
            if t is not None:
                t = '@%09.6f:' % t
                args = (t,) + args
            print(*args, **kwargs)

    def f(self, format_string, *args, **kwargs)            :
        """Same as print(fmt(...)).
        """
        return self(fmt(format_string, *args, **kwargs))


# Replace the standard module object for this module with a Printer object.
sys.modules[__name__] = Printer()
