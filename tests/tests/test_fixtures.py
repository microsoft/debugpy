import os
import sys
import pytest

pytest_plugins = ['pytester']


@pytest.mark.parametrize('use_ptvsd_logs', [True, False])
def test_logs_in_test_wrapper(testdir, use_ptvsd_logs):
    # Use the same conftest we usually use.
    with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'conftest.py'), 'r') as stream:
        conftest_contents = stream.read()

    testdir.makeconftest(conftest_contents)
    testdir.makepyfile(
        """
        import pytest
        import ptvsd
        import os
        import subprocess
        import sys

        def create_pydevd_log_file():
            subprocess.call([
                sys.executable,
                '-c',
                "from ptvsd._vendored import force_pydevd;"
                "from _pydev_bundle import pydev_log;"
                "pydev_log.critical('ERROR LOGGED TO PYDEVD LOG')"
            ])

        def test_error():
            create_pydevd_log_file()
            assert False

        def test_ok():
            create_pydevd_log_file()
            assert True
        """
    )
    testdir.monkeypatch.setenv("PYTHONPATH", os.pathsep.join(sys.path))

    def find_and_remove_from_set(s, expected_condition):
        for f in s.copy():
            if expected_condition(f):
                s.discard(f)
                return f
        raise AssertionError('Could not find expected condition in %s' % (s,))

    args = []
    if use_ptvsd_logs:
        args.append('--ptvsd-logs')
    result = testdir.runpytest_subprocess(*args)

    result.assert_outcomes(failed=1, passed=1)

    tmpdir = testdir.tmpdir
    logs_dir = os.path.join(str(tmpdir), 'tests', '_logs')
    if not use_ptvsd_logs:
        assert not os.path.isdir(logs_dir)
        runpytest_dir = os.path.join(str(tmpdir), 'runpytest-0')
        assert os.path.isdir(runpytest_dir)
        for dirname in ['test_error0', 'test_ok0']:
            dir_contents = set(os.listdir(os.path.join(runpytest_dir, dirname)))
            find_and_remove_from_set(dir_contents, lambda f: f.startswith('pydevd') and f.endswith('.log'))

        full_contents = ('\n'.join(result.outlines) + '\n'.join(result.errlines))
        assert full_contents.count('ERROR LOGGED TO PYDEVD LOG') == 1  # Should show on error.
    else:
        assert os.path.isdir(logs_dir)
        dir_contents = os.listdir(logs_dir)
        assert len(dir_contents) == 1
        logs_dir = os.path.join(logs_dir, next(iter(dir_contents)))

        test_logs_dir = os.path.join(logs_dir, 'test_logs_in_test_wrapper.py')
        assert os.path.isdir(test_logs_dir)
        expected_test_dirs = ['test_error', 'test_ok']
        assert set(os.listdir(test_logs_dir)) == set(expected_test_dirs)

        for d in expected_test_dirs:
            found_in_test_dir = set(os.listdir(os.path.join(test_logs_dir, d)))

            # Make sure we find and remove the ones which have the pid in it.
            find_and_remove_from_set(found_in_test_dir, lambda f: f.startswith('pydevd') and f.endswith('.log'))
            find_and_remove_from_set(found_in_test_dir, lambda f: f.startswith('tests-') and f.endswith('.log'))

            expected = set([
                'call_report.log',
                'call_report.stderr.log',
                'call_report.stdout.log',
                'setup_report.log',
                'setup_report.stderr.log',
                'setup_report.stdout.log',
            ])
            if d == 'test_error':
                expected.add('FAILED.log')

            assert expected == found_in_test_dir

