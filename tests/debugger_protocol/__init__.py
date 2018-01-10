import sys
import unittest


if sys.version_info[0] == 2:
    raise unittest.SkipTest('not tested under Python 2')
