import os
import unittest
import ptvsd.untangle

from ptvsd.wrapper import InternalsFilter


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
