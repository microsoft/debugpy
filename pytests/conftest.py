# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

import inspect
import pytest
import threading
import types

from .helpers.session import DebugSession


@pytest.fixture
def daemon():
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


@pytest.fixture(params=[
    'launch', 'attach_socket'  # 'attach_pid'
])
def debug_session(request):
    session = DebugSession(request.param)
    yield session
    try:
        session.wait_for_exit()
    finally:
        session.stop()
