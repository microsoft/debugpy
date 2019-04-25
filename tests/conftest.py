# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

import inspect
import os
import platform
import pytest
import threading
import types
import sys
import site

from . import helpers
from .helpers.printer import wait_for_output
import pytest_timeout
import tempfile

_original_dump_stacks = pytest_timeout.dump_stacks


def _print_pydevd_log(reason):
    sys.stderr.write('\n******************************************************************\n')
    sys.stderr.write('pydevd log on %s\n' % (reason,))
    sys.stderr.write('******************************************************************\n')
    current_pydevd_debug_file = os.environ.get('PYDEVD_DEBUG_FILE')
    if current_pydevd_debug_file:
        if os.path.exists(current_pydevd_debug_file):
            with open(current_pydevd_debug_file, 'r') as stream:
                sys.stderr.write(stream.read())
    sys.stderr.write('\n******************************************************************\n')
    sys.stderr.write('******************************************************************\n')


def _on_dump_stack_print_pydevd_log():
    # On timeout we also want to print the pydev log.
    _print_pydevd_log('timeout')
    _original_dump_stacks()


pytest_timeout.dump_stacks = _on_dump_stack_print_pydevd_log


def pytest_report_header(config):
    try:
        import multiprocessing
    except ImportError:
        pass
    else:
        print('Number of processors: %s' % (multiprocessing.cpu_count(),))

    print('Relevant system paths:')
    print('sys.prefix: %s' % (sys.prefix,))

    if hasattr(sys, 'base_prefix'):
        print('sys.base_prefix: %s' % (sys.base_prefix,))

    if hasattr(sys, 'real_prefix'):
        print('sys.real_prefix: %s' % (sys.real_prefix,))

    if hasattr(site, 'getusersitepackages'):
        print('site.getusersitepackages(): %s' % (site.getusersitepackages(),))

    if hasattr(site, 'getsitepackages'):
        print('site.getsitepackages(): %s' % (site.getsitepackages(),))

    for path in sys.path:
        if os.path.exists(path) and os.path.basename(path) == 'site-packages':
            print('Folder with "site-packages" in sys.path: %s' % (path,))


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item, call):
    # Adds attributes such as setup_result, call_result etc to the item after the
    # corresponding scope finished running its tests. This can be used in function-level
    # fixtures to detect failures, e.g.:
    #
    #   if request.node.call_result.failed: ...

    outcome = yield
    result = outcome.get_result()
    setattr(item, result.when + '_result', result)


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_pyfunc_call(pyfuncitem):
    # Resets the timestamp to zero for every new test, and ensures that
    # all output is printed after the test.
    helpers.timestamp_zero = helpers.clock()
    yield
    wait_for_output()


@pytest.fixture(autouse=True)
def _add_pydevd_output(request, tmpdir):
    current_pydevd_debug_file = tempfile.mktemp(suffix='.log', prefix='pydevd_output_%s' % (os.getpid(),), dir=str(tmpdir))
    os.environ['PYDEVD_DEBUG'] = 'True'
    os.environ['PYDEVD_DEBUG_FILE'] = current_pydevd_debug_file
    yield
    if request.node.setup_result.failed:
        _print_pydevd_log('test failure')
    elif request.node.setup_result.passed:
        if request.node.call_result.failed:
            _print_pydevd_log('test failure')


@pytest.fixture
def daemon(request):
    """Provides a factory function for daemon threads. The returned thread is
    started immediately, and it must not be alive by the time the test returns.
    """

    daemons = []

    def factory(func, name_suffix=''):
        name = func.__name__ + name_suffix
        thread = threading.Thread(target=func, name=name)
        thread.daemon = True
        daemons.append(thread)
        thread.start()
        return thread

    yield factory

    try:
        failed = request.node.call_result.failed
    except AttributeError:
        pass
    else:
        if not failed:
            for thread in daemons:
                assert not thread.is_alive()


@pytest.fixture
def pyfile(request, tmpdir):
    """A fixture providing a factory function that generates .py files.

    The returned factory takes a single function with an empty argument list,
    generates a temporary file that contains the code corresponding to the
    function body, and returns the full path to the generated file. Idiomatic
    use is as a decorator, e.g.:

        @pyfile
        def script_file():
            print('fizz')
            print('buzz')

    will produce a temporary file named script_file.py containing:

        print('fizz')
        print('buzz')

    and the variable script_file will contain the path to that file.

    In order for the factory to be able to extract the function body properly,
    function header ("def") must all be on a single line, with nothing after
    the colon but whitespace.
    """

    def factory(source):
        assert isinstance(source, types.FunctionType)
        name = source.__name__
        source, _ = inspect.getsourcelines(source)

        # First, find the "def" line.
        def_lineno = 0
        for line in source:
            line = line.strip()
            if line.startswith('def') and line.endswith(':'):
                break
            def_lineno += 1
        else:
            raise ValueError('Failed to locate function header.')

        # Remove everything up to and including "def".
        source = source[def_lineno + 1:]
        assert source

        # Now we need to adjust indentation. Compute how much the first line of
        # the body is indented by, then dedent all lines by that amount. Blank
        # lines don't matter indentation-wise, and might not be indented to begin
        # with, so just replace them with a simple newline.
        line = source[0]
        indent = len(line) - len(line.lstrip())
        source = [line[indent:] if line.strip() else '\n' for line in source]

        # Write it to file.
        source = ''.join(source)
        tmpfile = tmpdir.join(name + '.py')
        assert not tmpfile.check()
        # NOTE: This is a requirement with using pyfile. Adding this
        # makes it easier to add import start method
        assert 'import_and_enable_debugger' in source
        tmpfile.write(source)
        return tmpfile.strpath

    return factory


if os.environ.get('PTVSD_SIMPLE_TESTS', '').lower() in ('1', 'true'):
    # Setting PTVSD_SIMPLE_TESTS locally is useful to not have to run
    # all the test permutations while developing.
    _ATTACH_PARAMS = [
        'launch',
    ]

    _RUN_AS_PARAMS = [
        'file',
    ]
else:
    _ATTACH_PARAMS = [
        'launch',
        'attach_socket_cmdline',
        # 'attach_socket_import',
        # 'attach_pid',
    ]
    _ATTACH_PARAMS += ['attach_socket_import'] if platform.system() == 'Windows' else []

    _RUN_AS_PARAMS = [
        'file',
        'module',
    ]


@pytest.fixture(
    name='run_as',
    params=_RUN_AS_PARAMS
)
def _run_as(request):
    return request.param


@pytest.fixture(
    name='start_method',
    params=_ATTACH_PARAMS
)
def start_method(request):
    return request.param
