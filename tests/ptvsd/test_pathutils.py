import os
import os.path
import platform
import unittest

from ptvsd.pathutils import PathUnNormcase


def _find_file(filename):
    filename = os.path.normcase(os.path.normpath(filename))
    drive = os.path.splitdrive(filename)[0]
    found = []
    while True:
        dirname, basename = os.path.split(filename)
        for name in os.listdir(dirname or '.'):
            if os.path.normcase(name) == basename:
                found.insert(0, name)
                break
        else:
            raise Exception('oops: {}'.format(dirname))

        if not dirname or dirname == drive or dirname == drive + os.path.sep:
            return dirname.upper() + os.path.sep.join(found)
        filename = dirname


FILENAME = __file__
ACTUAL = _find_file(FILENAME)


class PathUtilTests(unittest.TestCase):
    def test_invalid_path_names(self):
        tool = PathUnNormcase()
        file_path = 'x:/this is an/invalid/file/invalid_file_.csv'
        result = tool.un_normcase(file_path)

        self.assertEqual(result, file_path)

    def test_empty_path_names(self):
        tool = PathUnNormcase()
        file_path = ''
        result = tool.un_normcase(file_path)

        self.assertEqual(result, file_path)

    def test_valid_names(self):
        tool = PathUnNormcase()
        result = tool.un_normcase(FILENAME)

        self.assertEqual(result, FILENAME)

    def test_path_names_normcased(self):
        tool = PathUnNormcase()
        tool.enable()
        result = tool.un_normcase(
                os.path.normcase(FILENAME))

        self.assertEqual(result, ACTUAL)

    @unittest.skipIf(platform.system() != 'Windows',
                     "Windows OS specific test")
    def test_path_names_uppercase_disabled(self):
        tool = PathUnNormcase()
        result = tool.un_normcase(FILENAME.upper())

        self.assertEqual(result, FILENAME)

    @unittest.skipIf(platform.system() != 'Windows',
                     "Windows OS specific test")
    def test_path_names_uppercase_enabled(self):
        tool = PathUnNormcase()
        tool.enable()
        result = tool.un_normcase(FILENAME.upper())

        self.assertEqual(result, ACTUAL)

    @unittest.skipIf(platform.system() != 'Windows',
                     "Windows OS specific test")
    def test_path_names_lowercase_disabled(self):
        tool = PathUnNormcase()
        result = tool.un_normcase(FILENAME.lower())

        self.assertEqual(result, FILENAME)

    @unittest.skipIf(platform.system() != 'Windows',
                     "Windows OS specific test")
    def test_path_names_lowercase_enabled(self):
        tool = PathUnNormcase()
        tool.enable()
        result = tool.un_normcase(FILENAME.lower())

        self.assertEqual(result, ACTUAL)
