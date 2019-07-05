# coding: utf-8
import os.path
from _pydevd_bundle.pydevd_constants import IS_WINDOWS, IS_PY2
from _pydev_bundle._pydev_filesystem_encoding import getfilesystemencoding
import io
from _pydev_bundle.pydev_log import log_context


def test_convert_utilities(tmpdir):
    import pydevd_file_utils

    test_dir = str(tmpdir.mkdir("Test_Convert_Utilities"))

    if IS_WINDOWS:
        normalized = pydevd_file_utils.normcase(test_dir)
        assert isinstance(normalized, str)  # bytes on py2, unicode on py3
        assert normalized.lower() == normalized

        upper_version = os.path.join(test_dir, 'ÁÉÍÓÚ')
        with open(upper_version, 'w') as stream:
            stream.write('test')

        with open(upper_version, 'r') as stream:
            assert stream.read() == 'test'

        with open(pydevd_file_utils.normcase(upper_version), 'r') as stream:
            assert stream.read() == 'test'

        assert '~' not in normalized

        for i in range(3):  # Check if cache is ok.

            if i == 2:
                pydevd_file_utils._listdir_cache.clear()

            assert pydevd_file_utils.get_path_with_real_case('<does not EXIST>') == '<does not EXIST>'
            real_case = pydevd_file_utils.get_path_with_real_case(normalized)
            assert isinstance(real_case, str)  # bytes on py2, unicode on py3
            # Note test_dir itself cannot be compared with because pytest may
            # have passed the case normalized.
            assert real_case.endswith("Test_Convert_Utilities")

            if i == 2:
                # Check that we have the expected paths in the cache.
                assert pydevd_file_utils._listdir_cache[os.path.dirname(normalized).lower()] == ['Test_Convert_Utilities']
                assert pydevd_file_utils._listdir_cache[(os.path.dirname(normalized).lower(), 'Test_Convert_Utilities'.lower())] == real_case

            if IS_PY2:
                # Test with unicode in python 2 too.
                real_case = pydevd_file_utils.get_path_with_real_case(normalized.decode(
                    getfilesystemencoding()))
                assert isinstance(real_case, str)  # bytes on py2, unicode on py3
                # Note test_dir itself cannot be compared with because pytest may
                # have passed the case normalized.
                assert real_case.endswith("Test_Convert_Utilities")

        # Check that it works with a shortened path.
        shortened = pydevd_file_utils.convert_to_short_pathname(normalized)
        assert '~' in shortened
        with_real_case = pydevd_file_utils.get_path_with_real_case(shortened)
        assert with_real_case.endswith('Test_Convert_Utilities')
        assert '~' not in with_real_case

    else:
        # On other platforms, nothing should change
        assert pydevd_file_utils.normcase(test_dir) == test_dir
        assert pydevd_file_utils.get_path_with_real_case(test_dir) == test_dir


def test_source_reference(tmpdir):
    import pydevd_file_utils

    pydevd_file_utils.set_ide_os('WINDOWS')
    if IS_WINDOWS:
        # Client and server are on windows.
        pydevd_file_utils.setup_client_server_paths([('c:\\foo', 'c:\\bar')])

        assert pydevd_file_utils.norm_file_to_client('c:\\bar\\my') == 'c:\\foo\\my'
        assert pydevd_file_utils.get_client_filename_source_reference('c:\\foo\\my') == 0

        assert pydevd_file_utils.norm_file_to_client('c:\\another\\my') == 'c:\\another\\my'
        source_reference = pydevd_file_utils.get_client_filename_source_reference('c:\\another\\my')
        assert source_reference != 0
        assert pydevd_file_utils.get_server_filename_from_source_reference(source_reference) == 'c:\\another\\my'

    else:
        # Client on windows and server on unix
        pydevd_file_utils.set_ide_os('WINDOWS')

        pydevd_file_utils.setup_client_server_paths([('c:\\foo', '/bar')])

        assert pydevd_file_utils.norm_file_to_client('/bar/my') == 'c:\\foo\\my'
        assert pydevd_file_utils.get_client_filename_source_reference('c:\\foo\\my') == 0

        assert pydevd_file_utils.norm_file_to_client('/another/my') == '\\another\\my'
        source_reference = pydevd_file_utils.get_client_filename_source_reference('\\another\\my')
        assert source_reference != 0
        assert pydevd_file_utils.get_server_filename_from_source_reference(source_reference) == '/another/my'


def test_to_server_and_to_client(tmpdir):
    try:

        def check(obtained, expected):
            assert obtained == expected, '%s (%s) != %s (%s)' % (obtained, type(obtained), expected, type(expected))
            assert isinstance(obtained, str)  # bytes on py2, unicode on py3
            assert isinstance(expected, str)  # bytes on py2, unicode on py3

        import pydevd_file_utils
        if IS_WINDOWS:
            # Check with made-up files

            pydevd_file_utils.setup_client_server_paths([('c:\\foo', 'c:\\bar'), ('c:\\foo2', 'c:\\bar2')])

            stream = io.StringIO()
            with log_context(0, stream=stream):
                pydevd_file_utils.norm_file_to_server('y:\\only_exists_in_client_not_in_server')
            assert r'pydev debugger: unable to find translation for: "y:\only_exists_in_client_not_in_server" in ["c:\foo", "c:\foo2"] (please revise your path mappings).' in stream.getvalue()

            # Client and server are on windows.
            pydevd_file_utils.set_ide_os('WINDOWS')
            for in_eclipse, in_python  in ([
                    ('c:\\foo', 'c:\\bar'),
                    ('c:/foo', 'c:\\bar'),
                    ('c:\\foo', 'c:/bar'),
                    ('c:\\foo', 'c:\\bar\\'),
                    ('c:/foo', 'c:\\bar\\'),
                    ('c:\\foo', 'c:/bar/'),
                    ('c:\\foo\\', 'c:\\bar'),
                    ('c:/foo/', 'c:\\bar'),
                    ('c:\\foo\\', 'c:/bar'),

                ]):
                PATHS_FROM_ECLIPSE_TO_PYTHON = [
                    (in_eclipse, in_python)
                ]
                pydevd_file_utils.setup_client_server_paths(PATHS_FROM_ECLIPSE_TO_PYTHON)
                check(pydevd_file_utils.norm_file_to_server('c:\\foo\\my'), 'c:\\bar\\my')
                check(pydevd_file_utils.norm_file_to_server('c:/foo/my'), 'c:\\bar\\my')
                check(pydevd_file_utils.norm_file_to_server('c:/foo/my/'), 'c:\\bar\\my')
                check(pydevd_file_utils.norm_file_to_server('c:\\foo\\áéíóú'.upper()), 'c:\\bar\\áéíóú')
                check(pydevd_file_utils.norm_file_to_client('c:\\bar\\my'), 'c:\\foo\\my')

            # Client on unix and server on windows
            pydevd_file_utils.set_ide_os('UNIX')
            for in_eclipse, in_python  in ([
                    ('/foo', 'c:\\bar'),
                    ('/foo', 'c:/bar'),
                    ('/foo', 'c:\\bar\\'),
                    ('/foo', 'c:/bar/'),
                    ('/foo/', 'c:\\bar'),
                    ('/foo/', 'c:\\bar\\'),
                ]):

                PATHS_FROM_ECLIPSE_TO_PYTHON = [
                    (in_eclipse, in_python)
                ]
                pydevd_file_utils.setup_client_server_paths(PATHS_FROM_ECLIPSE_TO_PYTHON)
                check(pydevd_file_utils.norm_file_to_server('/foo/my'), 'c:\\bar\\my')
                check(pydevd_file_utils.norm_file_to_client('c:\\bar\\my'), '/foo/my')
                check(pydevd_file_utils.norm_file_to_client('c:\\bar\\my\\'), '/foo/my')
                check(pydevd_file_utils.norm_file_to_client('c:/bar/my'), '/foo/my')
                check(pydevd_file_utils.norm_file_to_client('c:/bar/my/'), '/foo/my')

            # Test with 'real' files
            # Client and server are on windows.
            pydevd_file_utils.set_ide_os('WINDOWS')

            test_dir = str(tmpdir.mkdir("Foo"))
            os.makedirs(os.path.join(test_dir, "Another"))

            in_eclipse = os.path.join(os.path.dirname(test_dir), 'Bar')
            in_python = test_dir
            PATHS_FROM_ECLIPSE_TO_PYTHON = [
                (in_eclipse, in_python)
            ]
            pydevd_file_utils.setup_client_server_paths(PATHS_FROM_ECLIPSE_TO_PYTHON)

            assert pydevd_file_utils.norm_file_to_server(in_eclipse) == in_python.lower()
            found_in_eclipse = pydevd_file_utils.norm_file_to_client(in_python)
            assert found_in_eclipse.endswith('Bar')

            assert pydevd_file_utils.norm_file_to_server(
                os.path.join(in_eclipse, 'another')) == os.path.join(in_python, 'another').lower()
            found_in_eclipse = pydevd_file_utils.norm_file_to_client(
                os.path.join(in_python, 'another'))
            assert found_in_eclipse.endswith('Bar\\Another')

            # Client on unix and server on windows
            pydevd_file_utils.set_ide_os('UNIX')
            in_eclipse = '/foo'
            in_python = test_dir
            PATHS_FROM_ECLIPSE_TO_PYTHON = [
                (in_eclipse, in_python)
            ]
            pydevd_file_utils.setup_client_server_paths(PATHS_FROM_ECLIPSE_TO_PYTHON)
            assert pydevd_file_utils.norm_file_to_server('/foo').lower() == in_python.lower()
            assert pydevd_file_utils.norm_file_to_client(in_python) == in_eclipse

            # Test without translation in place (still needs to fix case and separators)
            pydevd_file_utils.set_ide_os('WINDOWS')
            PATHS_FROM_ECLIPSE_TO_PYTHON = []
            pydevd_file_utils.setup_client_server_paths(PATHS_FROM_ECLIPSE_TO_PYTHON)
            assert pydevd_file_utils.norm_file_to_server(test_dir) == test_dir.lower()
            assert pydevd_file_utils.norm_file_to_client(test_dir).endswith('\\Foo')
        else:
            # Client on windows and server on unix
            pydevd_file_utils.set_ide_os('WINDOWS')
            for in_eclipse, in_python  in ([
                    ('c:\\foo', '/báéíóúr'),
                    ('c:/foo', '/báéíóúr'),
                    ('c:/foo/', '/báéíóúr'),
                    ('c:/foo/', '/báéíóúr/'),
                    ('c:\\foo\\', '/báéíóúr/'),
                ]):

                PATHS_FROM_ECLIPSE_TO_PYTHON = [
                    (in_eclipse, in_python)
                ]

                pydevd_file_utils.setup_client_server_paths(PATHS_FROM_ECLIPSE_TO_PYTHON)
                assert pydevd_file_utils.norm_file_to_server('c:\\foo\\my') == '/báéíóúr/my'
                assert pydevd_file_utils.norm_file_to_server('C:\\foo\\my') == '/báéíóúr/my'
                assert pydevd_file_utils.norm_file_to_server('C:\\foo\\MY') == '/báéíóúr/MY'
                assert pydevd_file_utils.norm_file_to_server('C:\\foo\\MY\\') == '/báéíóúr/MY'
                assert pydevd_file_utils.norm_file_to_server('c:\\foo\\my\\file.py') == '/báéíóúr/my/file.py'
                assert pydevd_file_utils.norm_file_to_server('c:\\foo\\my\\other\\file.py') == '/báéíóúr/my/other/file.py'
                assert pydevd_file_utils.norm_file_to_server('c:/foo/my') == '/báéíóúr/my'
                assert pydevd_file_utils.norm_file_to_server('c:\\foo\\my\\') == '/báéíóúr/my'
                assert pydevd_file_utils.norm_file_to_server('c:/foo/my/') == '/báéíóúr/my'

                assert pydevd_file_utils.norm_file_to_client('/báéíóúr/my') == 'c:\\foo\\my'
                assert pydevd_file_utils.norm_file_to_client('/báéíóúr/my/') == 'c:\\foo\\my'

                # Files for which there's no translation have only their separators updated.
                assert pydevd_file_utils.norm_file_to_client('/usr/bin/x.py') == '\\usr\\bin\\x.py'
                assert pydevd_file_utils.norm_file_to_client('/usr/bin') == '\\usr\\bin'
                assert pydevd_file_utils.norm_file_to_client('/usr/bin/') == '\\usr\\bin'
                assert pydevd_file_utils.norm_file_to_server('\\usr\\bin') == '/usr/bin'
                assert pydevd_file_utils.norm_file_to_server('\\usr\\bin\\') == '/usr/bin'

                # When we have a client file and there'd be no translation, and making it absolute would
                # do something as '$cwd/$file_received' (i.e.: $cwd/c:/another in the case below),
                # warn the user that it's not correct and the path that should be translated instead
                # and don't make it absolute.
                assert pydevd_file_utils.norm_file_to_server('c:\\another') == 'c:/another'

            # Client and server on unix
            pydevd_file_utils.set_ide_os('UNIX')
            in_eclipse = '/foo'
            in_python = '/báéíóúr'
            PATHS_FROM_ECLIPSE_TO_PYTHON = [
                (in_eclipse, in_python)
            ]
            pydevd_file_utils.setup_client_server_paths(PATHS_FROM_ECLIPSE_TO_PYTHON)
            assert pydevd_file_utils.norm_file_to_server('/foo/my') == '/báéíóúr/my'
            assert pydevd_file_utils.norm_file_to_client('/báéíóúr/my') == '/foo/my'
    finally:
        pydevd_file_utils.setup_client_server_paths([])


def test_zip_paths(tmpdir):
    import pydevd_file_utils
    import sys
    import zipfile

    for i, zip_basename in enumerate(('MY1.zip', 'my2.egg!')):
        zipfile_path = str(tmpdir.join(zip_basename))
        zip_file = zipfile.ZipFile(zipfile_path, 'w')
        zip_file.writestr('zipped%s/__init__.py' % (i,), '')
        zip_file.writestr('zipped%s/zipped_contents.py' % (i,), 'def call_in_zip():\n    return 1')
        zip_file.close()

        sys.path.append(zipfile_path)
        try:
            import importlib
        except ImportError:
            __import__('zipped%s' % (i,))  # Py2.6 does not have importlib
        else:
            importlib.import_module('zipped%s' % (i,))  # Check that it's importable.

        # Check that we can deal with the zip path.
        assert pydevd_file_utils.exists(zipfile_path)
        abspath, realpath, basename = pydevd_file_utils.get_abs_path_real_path_and_base_from_file(zipfile_path)
        if IS_WINDOWS:
            assert abspath == zipfile_path.lower()
            assert basename == zip_basename.lower()
        else:
            assert abspath == zipfile_path
            assert basename == zip_basename

        # Check that we can deal with zip contents.
        for path in [
                zipfile_path + '/zipped%s/__init__.py' % (i,),
                zipfile_path + '/zipped%s/zipped_contents.py' % (i,),
                zipfile_path + '\\zipped%s\\__init__.py' % (i,),
                zipfile_path + '\\zipped%s\\zipped_contents.py' % (i,),
            ]:
            assert pydevd_file_utils.exists(path), 'Expected exists to return True for path:\n%s' % (path,)
            abspath, realpath, basename = pydevd_file_utils.get_abs_path_real_path_and_base_from_file(path)
            assert pydevd_file_utils.exists(abspath), 'Expected exists to return True for path:\n%s' % (abspath,)
            assert pydevd_file_utils.exists(realpath), 'Expected exists to return True for path:\n%s' % (realpath,)

        assert zipfile_path in pydevd_file_utils._ZIP_SEARCH_CACHE, '%s not in %s' % (
            zipfile_path, '\n'.join(sorted(pydevd_file_utils._ZIP_SEARCH_CACHE.keys())))


def test_source_mapping():

    from _pydevd_bundle.pydevd_source_mapping import SourceMapping, SourceMappingEntry
    source_mapping = SourceMapping()
    mapping = [
        SourceMappingEntry(line=3, end_line=6, runtime_line=5, runtime_source='<cell1>'),
        SourceMappingEntry(line=10, end_line=11, runtime_line=1, runtime_source='<cell2>'),
    ]
    source_mapping.set_source_mapping('file1.py', mapping)

    # Map to server
    assert source_mapping.map_to_server('file1.py', 1) == ('file1.py', 1, False)
    assert source_mapping.map_to_server('file1.py', 2) == ('file1.py', 2, False)

    assert source_mapping.map_to_server('file1.py', 3) == ('<cell1>', 5, True)
    assert source_mapping.map_to_server('file1.py', 4) == ('<cell1>', 6, True)
    assert source_mapping.map_to_server('file1.py', 5) == ('<cell1>', 7, True)
    assert source_mapping.map_to_server('file1.py', 6) == ('<cell1>', 8, True)

    assert source_mapping.map_to_server('file1.py', 7) == ('file1.py', 7, False)

    assert source_mapping.map_to_server('file1.py', 10) == ('<cell2>', 1, True)
    assert source_mapping.map_to_server('file1.py', 11) == ('<cell2>', 2, True)

    assert source_mapping.map_to_server('file1.py', 12) == ('file1.py', 12, False)

    # Map to client
    assert source_mapping.map_to_client('file1.py', 1) == ('file1.py', 1, False)
    assert source_mapping.map_to_client('file1.py', 2) == ('file1.py', 2, False)

    assert source_mapping.map_to_client('<cell1>', 5) == ('file1.py', 3, True)
    assert source_mapping.map_to_client('<cell1>', 6) == ('file1.py', 4, True)
    assert source_mapping.map_to_client('<cell1>', 7) == ('file1.py', 5, True)
    assert source_mapping.map_to_client('<cell1>', 8) == ('file1.py', 6, True)

    assert source_mapping.map_to_client('file1.py', 7) == ('file1.py', 7, False)

    assert source_mapping.map_to_client('<cell2>', 1) == ('file1.py', 10, True)
    assert source_mapping.map_to_client('<cell2>', 2) == ('file1.py', 11, True)

    assert source_mapping.map_to_client('file1.py', 12) == ('file1.py', 12, False)

