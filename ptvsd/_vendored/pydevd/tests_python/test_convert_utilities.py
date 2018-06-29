import os.path


def test_convert_utilities(tmpdir):
    import pydevd_file_utils
    import sys
    
    test_dir = str(tmpdir.mkdir("Test_Convert_Utilities"))
    if sys.platform == 'win32':
        normalized = pydevd_file_utils.normcase(test_dir)
        assert normalized.lower() == normalized
         
        assert '~' not in normalized
        assert '~' in pydevd_file_utils.convert_to_short_pathname(normalized)
         
        real_case = pydevd_file_utils.get_path_with_real_case(normalized)
        # Note test_dir itself cannot be compared with because pytest may
        # have passed the case normalized.
        assert real_case.endswith("Test_Convert_Utilities")
         
    else:
        # On other platforms, nothing should change
        assert pydevd_file_utils.normcase(test_dir) == test_dir
        assert pydevd_file_utils.convert_to_short_pathname(test_dir) == test_dir
        assert pydevd_file_utils.get_path_with_real_case(test_dir) == test_dir


def test_to_server_and_to_client(tmpdir):
    try:
        import pydevd_file_utils
        import sys
        if sys.platform == 'win32':
            # Check with made-up files
            
            # Client and server are on windows. 
            pydevd_file_utils.set_ide_os('WINDOWS')
            in_eclipse = 'c:\\foo'
            in_python = 'c:\\bar'
            PATHS_FROM_ECLIPSE_TO_PYTHON = [
                (in_eclipse, in_python)
            ]
            pydevd_file_utils.setup_client_server_paths(PATHS_FROM_ECLIPSE_TO_PYTHON)
            assert pydevd_file_utils.norm_file_to_server('c:\\foo\\my') == 'c:\\bar\\my'
            assert pydevd_file_utils.norm_file_to_server('c:\\foo\\my'.upper()) == 'c:\\bar\\my'
            assert pydevd_file_utils.norm_file_to_client('c:\\bar\\my') == 'c:\\foo\\my'
            
            # Client on unix and server on windows
            pydevd_file_utils.set_ide_os('UNIX')
            in_eclipse = '/foo'
            in_python = 'c:\\bar'
            PATHS_FROM_ECLIPSE_TO_PYTHON = [
                (in_eclipse, in_python)
            ]
            pydevd_file_utils.setup_client_server_paths(PATHS_FROM_ECLIPSE_TO_PYTHON)
            assert pydevd_file_utils.norm_file_to_server('/foo/my') == 'c:\\bar\\my'
            assert pydevd_file_utils.norm_file_to_client('c:\\bar\\my') == '/foo/my'
            
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
            in_eclipse = 'c:\\foo'
            in_python = '/bar'
            PATHS_FROM_ECLIPSE_TO_PYTHON = [
                (in_eclipse, in_python)
            ]
            pydevd_file_utils.setup_client_server_paths(PATHS_FROM_ECLIPSE_TO_PYTHON)
            assert pydevd_file_utils.norm_file_to_server('c:\\foo\\my') == '/bar/my'
            assert pydevd_file_utils.norm_file_to_client('/bar/my') == 'c:\\foo\\my'

            # Files for which there's no translation have only their separators updated.
            assert pydevd_file_utils.norm_file_to_client('/usr/bin') == '\\usr\\bin'
            assert pydevd_file_utils.norm_file_to_server('\\usr\\bin') == '/usr/bin'

            # Client and server on unix
            pydevd_file_utils.set_ide_os('UNIX')
            in_eclipse = '/foo'
            in_python = '/bar'
            PATHS_FROM_ECLIPSE_TO_PYTHON = [
                (in_eclipse, in_python)
            ]
            pydevd_file_utils.setup_client_server_paths(PATHS_FROM_ECLIPSE_TO_PYTHON)
            assert pydevd_file_utils.norm_file_to_server('/foo/my') == '/bar/my'
            assert pydevd_file_utils.norm_file_to_client('/bar/my') == '/foo/my'
    finally:
        pydevd_file_utils.setup_client_server_paths([])
