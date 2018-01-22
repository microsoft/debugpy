import sys
import unittest


# The code under the debugger_protocol package isn't used
# by the debugger (it's used by schema-related tools).  So we don't need
# to support Python 2.
if sys.version_info[0] == 2:
    raise unittest.SkipTest('not tested under Python 2')
