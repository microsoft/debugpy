# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

import inspect
import os
import pytest
import threading
import types

from . import helpers
from .helpers.session import DebugSession


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
    # Resets the timestamp zero for every new test.
    helpers.timestamp_zero = helpers.clock()
    yield


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
        # the body is indented by, then dedent all lines by that amount.
        line = source[0]
        indent = len(line) - len(line.lstrip())
        source = [line[indent:] for line in source]
        source = ''.join(source)

        tmpfile = tmpdir.join(name + '.py')
        assert not tmpfile.check()
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
        'attach_socket',
        # 'attach_pid',
    ]

    _RUN_AS_PARAMS = [
        'file',
        'module',
    ]


@pytest.fixture(params=_ATTACH_PARAMS)
def debug_session(request):
    session = DebugSession(request.param)
    try:
        yield session
        try:
            failed = request.node.call_result.failed
        except AttributeError:
            pass
        else:
            if not failed:
                session.wait_for_exit()
    finally:
        session.stop()


@pytest.fixture(
    name='run_as',
    params=_RUN_AS_PARAMS
)
def _run_as(request):
    return request.param


@pytest.fixture
def simple_hit_paused_on_break(debug_session, pyfile, run_as):
    '''
    Starts debug session with a pre-defined code sample, yields with
    a breakpoint hit and when finished, resumes the execution
    and waits for the debug session to exit.

    :note: fixture will run with all permutations of the debug_session
    parameters as well as the run_as parameters.
    '''

    from pytests.helpers.timeline import Event

    @pyfile
    def code_to_debug():
        a = 1
        b = {"one": 1, "two": 2}
        c = 3
        print([a, b, c])

    bp_line = 4
    bp_file = code_to_debug
    debug_session.common_setup(bp_file, run_as, breakpoints=[bp_line])
    debug_session.start_debugging()
    hit = debug_session.wait_for_thread_stopped()

    yield hit

    debug_session.send_request('continue').wait_for_response()
    debug_session.wait_for_next(Event('continued'))

    debug_session.wait_for_exit()
