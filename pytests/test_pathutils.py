import os
import os.path
import platform
import pytest
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


def test_invalid_path_names():
    tool = PathUnNormcase()
    file_path = 'x:/this is an/invalid/file/invalid_file_.csv'
    result = tool.un_normcase(file_path)
    assert result == file_path


def test_empty_path_names():
    tool = PathUnNormcase()
    file_path = ''
    result = tool.un_normcase(file_path)
    assert result == file_path


def test_valid_names():
    tool = PathUnNormcase()
    result = tool.un_normcase(FILENAME)
    assert result == FILENAME


def test_path_names_normcased():
    tool = PathUnNormcase()
    tool.enable()
    result = tool.un_normcase(
            os.path.normcase(FILENAME))
    assert result == ACTUAL


@pytest.mark.skipif(platform.system() != 'Windows', reason='Windows OS specific test')
def test_path_names_uppercase_disabled():
    tool = PathUnNormcase()
    expected = FILENAME.upper()
    result = tool.un_normcase(expected)

    # Since path tool is disabled we should get the same
    # path back
    assert result == expected


@pytest.mark.skipif(platform.system() != 'Windows', reason='Windows OS specific test')
def test_path_names_uppercase_enabled():
    tool = PathUnNormcase()
    tool.enable()
    result = tool.un_normcase(FILENAME.upper())
    assert result == ACTUAL


@pytest.mark.skipif(platform.system() != 'Windows', reason='Windows OS specific test')
def test_path_names_lowercase_disabled():
    tool = PathUnNormcase()
    expected = FILENAME.lower()
    result = tool.un_normcase(expected)

    # Since path tool is disabled we should get the same
    # path back
    assert result == expected


@pytest.mark.skipif(platform.system() != 'Windows', reason='Windows OS specific test')
def test_path_names_lowercase_enabled():
    tool = PathUnNormcase()
    tool.enable()
    result = tool.un_normcase(FILENAME.lower())

    assert result == ACTUAL
