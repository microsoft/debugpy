# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import inspect
import os
import platform
import py.path
import pytest
import tempfile
import threading
import types

from ptvsd.common import compat, fmt, log, options, timestamp
from tests import code, pydevd_log
from tests.debug import runners, session, targets


# Set up the test matrix for various code types and attach methods. Most tests will
# use both run_as and start_method, so the matrix is a cross product of them.

if int(os.environ.get("PTVSD_SIMPLE_TESTS", "0")):
    TARGETS = [targets.Program]
    RUNNERS = [runners.launch, runners.attach_by_socket["cli"]]
else:
    TARGETS = targets.all_named
    RUNNERS = [
        runners.launch,
        runners.attach_by_socket["api"],
        runners.attach_by_socket["cli"],
    ]


@pytest.fixture(params=TARGETS)
def target(request):
    return request.param


@pytest.fixture(params=RUNNERS)
def run(request):
    return request.param


@pytest.fixture(autouse=True)
def test_wrapper(request, long_tmpdir):
    timestamp.reset()

    session.Session.tmpdir = long_tmpdir

    original_log_dir = None
    try:
        if options.log_dir is not None:
            original_log_dir = options.log_dir
            log_subdir = request.node.name
            for ch in r"\/:?*|<>":
                log_subdir = log_subdir.replace(ch, fmt("&#{0};", ord(ch)))
            options.log_dir += "/" + log_subdir
            try:
                py.path.local(options.log_dir).remove()
            except Exception:
                pass

        print("\n")  # make sure on-screen logs start on a new line
        with log.to_file(prefix="tests"):
            log.info("Test {0} started.", request.node.name)
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
                        "{0} for test {1} {2}.",
                        report.when,
                        request.node.name,
                        report.outcome,
                    )

                    if options.log_dir is not None:
                        with open(os.path.join(options.log_dir, report_attr + ".log"), "w") as f:
                            f.write(report.longreprtext)
                        with open(os.path.join(options.log_dir, report_attr + ".stdout.log"), "w") as f:
                            f.write(report.capstdout)
                        with open(os.path.join(options.log_dir, report_attr + ".stderr.log"), "w") as f:
                            f.write(report.capstderr)

                if failed and options.log_dir is not None:
                    with open(os.path.join(options.log_dir, "FAILED.log"), "w"):
                        pass
    finally:
        if original_log_dir is not None:
            options.log_dir = original_log_dir


@pytest.fixture(autouse=True)
def with_pydevd_log(request, tmpdir):
    """Enables pydevd logging during the test run, and dumps the log if the test fails.
    """

    prefix = "pydevd_debug_file-{0}".format(os.getpid())
    filename = tempfile.mktemp(suffix=".log", prefix=prefix, dir=str(tmpdir))

    with pydevd_log.enabled(filename):
        yield

    if request.node.setup_report.passed:
        if not request.node.call_report.failed:
            return
    elif not request.node.setup_report.failed:
        return

    pydevd_log.dump("failed")


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


if platform.system() != "Windows":

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
        source = [l[indent:] if l.strip() else "\n" for l in source]
        source = "".join(source)

        # Write it to file.
        tmpfile = long_tmpdir / (name + ".py")
        tmpfile.strpath = compat.filename(tmpfile.strpath)
        assert not tmpfile.check()
        tmpfile.write(source)

        tmpfile.lines = code.get_marked_line_numbers(tmpfile)
        return tmpfile

    return factory
