import unittest
import pydevd_file_utils

class TestFileUtils(unittest.TestCase):
    def test_path_search(self):
        self.assertTrue(pydevd_file_utils.contains_dir("foo/bar/inspect.py", "inspect.py")) 
        self.assertTrue(pydevd_file_utils.contains_dir("foo/bar/inspect.py", "foo"))
        self.assertTrue(pydevd_file_utils.contains_dir("foo/bar/inspect.py", "bar"))
        self.assertFalse(pydevd_file_utils.contains_dir("foo/bar/inspect.py", "boo"))
        self.assertFalse(pydevd_file_utils.contains_dir("foo/bar/inspect.py", "foo/bar"))
        self.assertFalse(pydevd_file_utils.contains_dir("<not a path>", "path"))