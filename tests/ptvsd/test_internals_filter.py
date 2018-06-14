import os
import unittest
import ptvsd.untangle

from ptvsd.wrapper import InternalsFilter
from ptvsd.wrapper import dont_trace_ptvsd_files


class InternalsFilterTests(unittest.TestCase):
    def test_internal_paths(self):
        int_filter = InternalsFilter()
        internal_dir = os.path.dirname(
            os.path.abspath(ptvsd.untangle.__file__)
        )
        internal_files = [
            os.path.abspath(ptvsd.untangle.__file__),
            # File used by VS Only
            os.path.join('somepath', 'ptvsd_launcher.py'),
            # Any file under ptvsd
            os.path.join(internal_dir, 'somefile.py'),
        ]
        for fp in internal_files:
            self.assertTrue(int_filter.is_internal_path(fp))

    def test_user_file_paths(self):
        int_filter = InternalsFilter()
        files = [
            __file__,
            os.path.join('somepath', 'somefile.py'),
        ]
        for fp in files:
            self.assertFalse(int_filter.is_internal_path(fp))


class PtvsdFileTraceFilter(unittest.TestCase):
    def test_basic(self):
        internal_dir = os.path.dirname(
            os.path.abspath(ptvsd.untangle.__file__))

        test_paths = {
            os.path.join(internal_dir, 'wrapper.py'): True,
            os.path.join(internal_dir, 'abcd', 'ptvsd', 'wrapper.py'): True,
            os.path.join(internal_dir, 'ptvsd', 'wrapper.py'): True,
            os.path.join(internal_dir, 'abcd', 'wrapper.py'): True,
            os.path.join('usr', 'abcd', 'ptvsd', 'wrapper.py'): False,
            os.path.join('C:', 'ptvsd', 'wrapper1.py'): False,
            os.path.join('C:', 'abcd', 'ptvsd', 'ptvsd.py'): False,
            os.path.join('usr', 'ptvsd', 'w.py'): False,
            os.path.join('ptvsd', 'w.py'): False,
            os.path.join('usr', 'abcd', 'ptvsd', 'tangle.py'): False,
        }

        for path, val in test_paths.items():
            self.assertTrue(val == dont_trace_ptvsd_files(path),
                            msg='Path  : %s\nActual: %s' % (path,
                                                            internal_dir))
