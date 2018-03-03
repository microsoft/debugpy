import os.path
import sys
import unittest
import platform

from ptvsd.pathutils import PathUnNormcase

class PathUtilTests(unittest.TestCase):
    def test_invalid_path_names(self):
        tool = PathUnNormcase()
        file_path = 'x:/this is an/invalid/file/invalid_file_.csv'
        self.assertEqual(file_path, tool.un_normcase(file_path))

    def test_empty_path_names(self):
        tool = PathUnNormcase()
        file_path = ''
        self.assertEqual(file_path, tool.un_normcase(file_path))

    def test_valid_names(self):
        tool = PathUnNormcase()
        file_path = __file__
        self.assertEqual(file_path, tool.un_normcase(file_path))

    def test_path_names_normcased(self):
        tool = PathUnNormcase()
        tool.enable()
        file_path = __file__
        self.assertEqual(file_path, tool.un_normcase(os.path.normcase(file_path)))

    @unittest.skipIf(platform.system() != 'Windows', "Windows OS specific test")
    def test_path_names_uppercase_disabled(self):
        tool = PathUnNormcase()
        file_path = __file__
        self.assertNotEqual(file_path, tool.un_normcase(file_path.upper()))

    @unittest.skipIf(platform.system() != 'Windows', "Windows OS specific test")
    def test_path_names_uppercase_enabled(self):
        tool = PathUnNormcase()
        tool.enable()
        file_path = __file__
        self.assertEqual(file_path, tool.un_normcase(file_path.upper()))

    @unittest.skipIf(platform.system() != 'Windows', "Windows OS specific test")
    def test_path_names_lowercase_disabled(self):
        tool = PathUnNormcase()
        file_path = __file__
        self.assertNotEqual(file_path, tool.un_normcase(file_path.lower()))

    @unittest.skipIf(platform.system() != 'Windows', "Windows OS specific test")
    def test_path_names_lowercase_enabled(self):
        tool = PathUnNormcase()
        tool.enable()
        file_path = __file__
        self.assertEqual(file_path, tool.un_normcase(file_path.lower()))
