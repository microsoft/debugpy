import threading

from _pydevd_bundle.pydevd_comm import pydevd_find_thread_by_id
from _pydevd_bundle.pydevd_utils import convert_dap_log_message_to_expression
from tests_python.debug_constants import IS_PY26, IS_PY3K
import sys
from _pydevd_bundle.pydevd_constants import IS_CPYTHON
import pytest


def test_is_main_thread():
    from _pydevd_bundle.pydevd_utils import is_current_thread_main_thread
    if not is_current_thread_main_thread():
        error_msg = 'Current thread does not seem to be a main thread. Details:\n'
        current_thread = threading.current_thread()
        error_msg += 'Current thread: %s\n' % (current_thread,)

        if hasattr(threading, 'main_thread'):
            error_msg += 'Main thread found: %s\n' % (threading.main_thread(),)
        else:
            error_msg += 'Current main thread not instance of: %s (%s)' % (
                threading._MainThread, current_thread.__class__.__mro__,)

        raise AssertionError(error_msg)

    class NonMainThread(threading.Thread):

        def run(self):
            self.is_main_thread = is_current_thread_main_thread()

    non_main_thread = NonMainThread()
    non_main_thread.start()
    non_main_thread.join()
    assert not non_main_thread.is_main_thread


def test_find_thread():
    from _pydevd_bundle.pydevd_constants import get_current_thread_id
    assert pydevd_find_thread_by_id('123') is None

    assert pydevd_find_thread_by_id(
        get_current_thread_id(threading.current_thread())) is threading.current_thread()


def check_dap_log_message(log_message, expected, evaluated, eval_locals=None):
    ret = convert_dap_log_message_to_expression(log_message)
    assert ret == expected
    assert (eval(ret, eval_locals)) == evaluated
    return ret


def test_convert_dap_log_message_to_expression():
    assert check_dap_log_message(
        'a',
        "'a'",
        'a',
    )
    assert check_dap_log_message(
        'a {a}',
        "'a %s' % (a,)",
        'a value',
        {'a': 'value'}
    )
    assert check_dap_log_message(
        'a {1}',
        "'a %s' % (1,)",
        'a 1'
    )
    assert check_dap_log_message(
        'a {  }',
        "'a '",
        'a '
    )
    assert check_dap_log_message(
        'a {1} {2}',
        "'a %s %s' % (1, 2,)",
        'a 1 2',
    )
    assert check_dap_log_message(
        'a {{22:22}} {2}',
        "'a %s %s' % ({22:22}, 2,)",
        'a {22: 22} 2'
    )
    assert check_dap_log_message(
        'a {(22,33)}} {2}',
        "'a %s} %s' % ((22,33), 2,)",
        'a (22, 33)} 2'
    )

    if not IS_PY26:
        # Note: set literal not valid for Python 2.6.
        assert check_dap_log_message(
            'a {{1: {1}}}',
            "'a %s' % ({1: {1}},)",
            'a {1: {1}}' if IS_PY3K else 'a {1: set([1])}',
        )

    # Error condition.
    assert check_dap_log_message(
        'a {{22:22} {2}',
        "'Unbalanced braces in: a {{22:22} {2}'",
        'Unbalanced braces in: a {{22:22} {2}'
    )


def test_pydevd_log():
    from _pydev_bundle import pydev_log
    try:
        import StringIO as io
    except:
        import io
    from _pydev_bundle.pydev_log import log_context

    stream = io.StringIO()
    with log_context(0, stream=stream):
        pydev_log.critical('always')
        pydev_log.info('never')

    assert stream.getvalue() == 'always\n'

    stream = io.StringIO()
    with log_context(1, stream=stream):
        pydev_log.critical('always')
        pydev_log.info('this too')

    assert stream.getvalue() == 'always\nthis too\n'

    stream = io.StringIO()
    with log_context(0, stream=stream):
        pydev_log.critical('always %s', 1)

    assert stream.getvalue() == 'always 1\n'

    stream = io.StringIO()
    with log_context(0, stream=stream):
        pydev_log.critical('always %s %s', 1, 2)

    assert stream.getvalue() == 'always 1 2\n'

    stream = io.StringIO()
    with log_context(0, stream=stream):
        pydev_log.critical('always %s %s', 1)

    # Even if there's an error in the formatting, don't fail, just print the message and args.
    assert stream.getvalue() == 'always %s %s - (1,)\n'

    stream = io.StringIO()
    with log_context(0, stream=stream):
        try:
            raise RuntimeError()
        except:
            pydev_log.exception('foo')

        assert 'foo\n' in stream.getvalue()
        assert 'raise RuntimeError()' in stream.getvalue()

    stream = io.StringIO()
    with log_context(0, stream=stream):
        pydev_log.error_once('always %s %s', 1)

    # Even if there's an error in the formatting, don't fail, just print the message and args.
    assert stream.getvalue() == 'always %s %s - (1,)\n'


def test_pydevd_logging_files(tmpdir):
    from _pydev_bundle import pydev_log
    from _pydevd_bundle.pydevd_constants import DebugInfoHolder
    import os.path
    from _pydev_bundle.pydev_log import _LoggingGlobals

    try:
        import StringIO as io
    except:
        import io
    from _pydev_bundle.pydev_log import log_context

    stream = io.StringIO()
    with log_context(0, stream=stream):
        d1 = str(tmpdir.join('d1'))
        d2 = str(tmpdir.join('d2'))

        for d in (d1, d2):
            DebugInfoHolder.PYDEVD_DEBUG_FILE = os.path.join(d, 'file.txt')
            pydev_log.initialize_debug_stream(force=True)

            assert os.path.normpath(_LoggingGlobals._debug_stream_filename) == \
                os.path.normpath(os.path.join(d, 'file.%s.txt' % os.getpid()))

            assert os.path.exists(_LoggingGlobals._debug_stream_filename)

            assert pydev_log.list_log_files(DebugInfoHolder.PYDEVD_DEBUG_FILE) == [
                _LoggingGlobals._debug_stream_filename]


def _check_tracing_other_threads():
    import pydevd_tracing
    import time
    from tests_python.debugger_unittest import wait_for_condition
    try:
        import _thread
    except ImportError:
        import thread as _thread

    def method():
        while True:
            trace_func = sys.gettrace()
            if trace_func:
                threading.current_thread().trace_func = trace_func
                break
            time.sleep(.01)

    def dummy_thread_method():
        threads.append(threading.current_thread())
        method()

    threads = []
    threads.append(threading.Thread(target=method))
    threads[-1].start()
    _thread.start_new_thread(dummy_thread_method, ())

    wait_for_condition(lambda: len(threads) == 2, msg=lambda:'Found threads: %s' % (threads,))

    def tracing_func(frame, event, args):
        return tracing_func

    assert pydevd_tracing.set_trace_to_threads(tracing_func) == 0

    def check_threads_tracing_func():
        for t in threads:
            if getattr(t, 'trace_func', None) != tracing_func:
                return False
        return True

    wait_for_condition(check_threads_tracing_func)

    assert tracing_func == sys.gettrace()


def _build_launch_env():
    import os
    import pydevd

    environ = os.environ.copy()
    cwd = os.path.abspath(os.path.dirname(__file__))
    assert os.path.isdir(cwd)

    resources_dir = os.path.join(os.path.dirname(pydevd.__file__), 'tests_python', 'resources')
    assert os.path.isdir(resources_dir)

    attach_to_process_dir = os.path.join(os.path.dirname(pydevd.__file__), 'pydevd_attach_to_process')
    assert os.path.isdir(attach_to_process_dir)

    pydevd_dir = os.path.dirname(pydevd.__file__)
    assert os.path.isdir(pydevd_dir)

    environ['PYTHONPATH'] = (
            cwd + os.pathsep +
            resources_dir + os.pathsep +
            attach_to_process_dir + os.pathsep +
            pydevd_dir + os.pathsep +
            environ.get('PYTHONPATH', '')
    )
    return cwd, environ


def _check_in_separate_process(method_name, module_name='test_utilities'):
    import subprocess
    cwd, environ = _build_launch_env()

    subprocess.check_call(
        [sys.executable, '-c', 'import %(module_name)s;%(module_name)s.%(method_name)s()' % dict(
            method_name=method_name, module_name=module_name)],
        env=environ,
        cwd=cwd
    )


@pytest.mark.skipif(not IS_CPYTHON, reason='Functionality to trace other threads requires CPython.')
def test_tracing_other_threads():
    # Note: run this test in a separate process so that it doesn't mess with any current tracing
    # in our current process.
    _check_in_separate_process('_check_tracing_other_threads')


@pytest.mark.skipif(not IS_CPYTHON, reason='Functionality to trace other threads requires CPython.')
def test_find_main_thread_id():
    # Note: run the checks below in a separate process because they rely heavily on what's available
    # in the env (such as threads or having threading imported).
    _check_in_separate_process('check_main_thread_id_simple', '_pydevd_test_find_main_thread_id')
    _check_in_separate_process('check_main_thread_id_multiple_threads', '_pydevd_test_find_main_thread_id')
    _check_in_separate_process('check_win_threads', '_pydevd_test_find_main_thread_id')
    _check_in_separate_process('check_fix_main_thread_id_multiple_threads', '_pydevd_test_find_main_thread_id')

    import subprocess
    import os
    import pydevd
    cwd, environ = _build_launch_env()

    subprocess.check_call(
        [sys.executable, '-m', '_pydevd_test_find_main_thread_id'],
        env=environ,
        cwd=cwd
    )

    resources_dir = os.path.join(os.path.dirname(pydevd.__file__), 'tests_python', 'resources')

    subprocess.check_call(
        [sys.executable, os.path.join(resources_dir, '_pydevd_test_find_main_thread_id.py') ],
        env=environ,
        cwd=cwd
    )
