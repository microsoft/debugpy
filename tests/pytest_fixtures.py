# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, division, print_function, unicode_literals

import inspect
import os
import py
import pytest
import sys
import threading
import types

from debugpy.common import compat, fmt, log, timestamp
import tests
from tests import code, logs
from tests.debug import runners, session, targets

# Set up the test matrix for various code types and attach methods

if tests.full:
    TARGETS = targets.all_named
    RUNNERS = runners.all_launch + runners.all_attach_socket
else:
    TARGETS = [targets.Program]
    RUNNERS = [runners.launch]


@pytest.fixture(params=TARGETS)
def target(request):
    return request.param


@pytest.fixture(params=RUNNERS)
def run(request):
    return request.param


@pytest.fixture(autouse=True)
def test_wrapper(request, long_tmpdir):
    def write_log(filename, data):
        filename = os.path.join(log.log_dir, filename)
        if not isinstance(data, bytes):
            data = data.encode("utf-8")
        with open(filename, "wb") as f:
            f.write(data)

    session.Session.reset_counter()

    session.Session.tmpdir = long_tmpdir
    original_log_dir = log.log_dir

    failed = True
    try:
        if log.log_dir is None:
            log.log_dir = (long_tmpdir / "debugpy_logs").strpath
        else:
            log_subdir = request.node.nodeid
            log_subdir = log_subdir.replace("::", "/")
            for ch in r":?*|<>":
                log_subdir = log_subdir.replace(ch, fmt("&#{0};", ord(ch)))
            log.log_dir += "/" + log_subdir

        try:
            py.path.local(log.log_dir).remove()
        except Exception:
            pass

        print("\n")  # make sure on-screen logs start on a new line
        with log.to_file(prefix="tests"):
            timestamp.reset()
            log.info("{0} started.", request.node.nodeid)
            try:
                yield
            finally:
                failed = False
                for report_attr in ("setup_report", "call_report", "teardown_report"):
                    try:
                        report = getattr(request.node, report_attr)
                    except AttributeError:
                        continue

                    failed |= report.failed
                    log.write_format(
                        "error" if report.failed else "info",
                        "pytest {0} phase for {1} {2}.",
                        report.when,
                        request.node.nodeid,
                        report.outcome,
                    )

                    write_log(report_attr + ".log", report.longreprtext)
                    write_log(report_attr + ".stdout.log", report.capstdout)
                    write_log(report_attr + ".stderr.log", report.capstderr)

                if failed:
                    write_log("FAILED.log", "")
                    logs.dump()

    finally:
        if not failed and not request.config.option.debugpy_log_passed:
            try:
                py.path.local(log.log_dir).remove()
            except Exception:
                pass
        log.log_dir = original_log_dir


@pytest.fixture
def daemon(request):
    """Provides a factory function for daemon threads. The returned thread is
    started immediately, and it must not be alive by the time the test returns.
    """

    daemons = []

    def factory(func, name_suffix=""):
        name = func.__name__ + name_suffix
        thread = threading.Thread(target=func, name=name)
        thread.daemon = True
        daemons.append(thread)
        thread.start()
        return thread

    yield factory

    try:
        failed = request.node.call_report.failed
    except AttributeError:
        pass
    else:
        if not failed:
            for thread in daemons:
                assert not thread.is_alive()


if sys.platform != "win32":

    @pytest.fixture
    def long_tmpdir(request, tmpdir):
        return tmpdir


else:
    import ctypes

    GetLongPathNameW = ctypes.windll.kernel32.GetLongPathNameW
    GetLongPathNameW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32]
    GetLongPathNameW.restype = ctypes.c_uint32

    @pytest.fixture
    def long_tmpdir(request, tmpdir):
        """Like tmpdir, but ensures that it's a long rather than short filename on Win32.
        """
        path = compat.filename(tmpdir.strpath)
        buffer = ctypes.create_unicode_buffer(512)
        if GetLongPathNameW(path, buffer, len(buffer)):
            path = buffer.value
        return py.path.local(path)


@pytest.fixture
def pyfile(request, long_tmpdir):
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

    Note that because the code is physically in a separate file when it runs,
    it cannot reuse top-level module imports - it must import all the modules
    that it uses locally. When linter complains, use #noqa.

    Returns a py.path.local instance that has the additional attribute "lines".
    After the source is writen to disk, tests.code.get_marked_line_numbers() is
    invoked on the resulting file to compute the value of that attribute.
    """

    def factory(source):
        assert isinstance(source, types.FunctionType)
        name = source.__name__
        source, _ = inspect.getsourcelines(source)

        # First, find the "def" line.
        def_lineno = 0
        for line in source:
            line = line.strip()
            if line.startswith("def") and line.endswith(":"):
                break
            def_lineno += 1
        else:
            raise ValueError("Failed to locate function header.")

        # Remove everything up to and including "def".
        source = source[def_lineno + 1 :]
        assert source

        # Now we need to adjust indentation. Compute how much the first line of
        # the body is indented by, then dedent all lines by that amount. Blank
        # lines don't matter indentation-wise, and might not be indented to begin
        # with, so just replace them with a simple newline.
        line = source[0]
        indent = len(line) - len(line.lstrip())
        source = [s[indent:] if s.strip() else "\n" for s in source]
        source = "".join(source)

        # Write it to file.
        tmpfile = long_tmpdir / (name + ".py")
        tmpfile.strpath = compat.filename(tmpfile.strpath)
        assert not tmpfile.check()
        tmpfile.write(source)

        tmpfile.lines = code.get_marked_line_numbers(tmpfile)
        return tmpfile

    return factory
