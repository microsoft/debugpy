
from _pydevd_bundle.pydevd_constants import get_frame, IS_CPYTHON, IS_64BIT_PROCESS, IS_WINDOWS, \
    IS_LINUX, IS_MAC
from _pydev_imps._pydev_saved_modules import thread, threading
from _pydev_bundle import pydev_log
from os.path import os
try:
    import ctypes
except ImportError:
    ctypes = None

try:
    import cStringIO as StringIO  # may not always be available @UnusedImport
except:
    try:
        import StringIO  # @Reimport
    except:
        import io as StringIO

import sys  # @Reimport
import traceback

_original_settrace = sys.settrace


class TracingFunctionHolder:
    '''This class exists just to keep some variables (so that we don't keep them in the global namespace).
    '''
    _original_tracing = None
    _warn = True
    _lock = thread.allocate_lock()
    _traceback_limit = 1
    _warnings_shown = {}


def get_exception_traceback_str():
    exc_info = sys.exc_info()
    s = StringIO.StringIO()
    traceback.print_exception(exc_info[0], exc_info[1], exc_info[2], file=s)
    return s.getvalue()


def _get_stack_str(frame):

    msg = '\nIf this is needed, please check: ' + \
          '\nhttp://pydev.blogspot.com/2007/06/why-cant-pydev-debugger-work-with.html' + \
          '\nto see how to restore the debug tracing back correctly.\n'

    if TracingFunctionHolder._traceback_limit:
        s = StringIO.StringIO()
        s.write('Call Location:\n')
        traceback.print_stack(f=frame, limit=TracingFunctionHolder._traceback_limit, file=s)
        msg = msg + s.getvalue()

    return msg


def _internal_set_trace(tracing_func):
    if TracingFunctionHolder._warn:
        frame = get_frame()
        if frame is not None and frame.f_back is not None:
            filename = frame.f_back.f_code.co_filename.lower()
            if not filename.endswith('threading.py') and not filename.endswith('pydevd_tracing.py'):

                message = \
                '\nPYDEV DEBUGGER WARNING:' + \
                '\nsys.settrace() should not be used when the debugger is being used.' + \
                '\nThis may cause the debugger to stop working correctly.' + \
                '%s' % _get_stack_str(frame.f_back)

                if message not in TracingFunctionHolder._warnings_shown:
                    # only warn about each message once...
                    TracingFunctionHolder._warnings_shown[message] = 1
                    sys.stderr.write('%s\n' % (message,))
                    sys.stderr.flush()

    if TracingFunctionHolder._original_tracing:
        TracingFunctionHolder._original_tracing(tracing_func)


def SetTrace(tracing_func):
    if TracingFunctionHolder._original_tracing is None:
        # This may happen before replace_sys_set_trace_func is called.
        sys.settrace(tracing_func)
        return

    try:
        TracingFunctionHolder._lock.acquire()
        TracingFunctionHolder._warn = False
        _internal_set_trace(tracing_func)
        TracingFunctionHolder._warn = True
    finally:
        TracingFunctionHolder._lock.release()


def replace_sys_set_trace_func():
    if TracingFunctionHolder._original_tracing is None:
        TracingFunctionHolder._original_tracing = sys.settrace
        sys.settrace = _internal_set_trace


def restore_sys_set_trace_func():
    if TracingFunctionHolder._original_tracing is not None:
        sys.settrace = TracingFunctionHolder._original_tracing
        TracingFunctionHolder._original_tracing = None


def set_trace_to_threads(tracing_func, target_threads=None):
    if not IS_CPYTHON or ctypes is None or sys.version_info[:2] > (3, 7):
        return -1

    if IS_WINDOWS:
        if IS_64BIT_PROCESS:
            suffix = 'amd64'
        else:
            suffix = 'x86'

        filename = os.path.join(os.path.dirname(__file__), 'pydevd_attach_to_process', 'attach_%s.dll' % (suffix,))

    elif IS_LINUX:
        if IS_64BIT_PROCESS:
            suffix = 'amd64'
        else:
            suffix = 'x86'

        filename = os.path.join(os.path.dirname(__file__), 'pydevd_attach_to_process', 'attach_linux_%s.so' % (suffix,))

    elif IS_MAC:
        if IS_64BIT_PROCESS:
            suffix = 'x86_64.dylib'
        else:
            suffix = 'x86.dylib'

        filename = os.path.join(os.path.dirname(__file__), 'pydevd_attach_to_process', 'attach_%s' % (suffix,))

    else:
        pydev_log.info('Unable to set trace to all threads in platform: %s', sys.platform)
        return -1

    if not os.path.exists(filename):
        pydev_log.critical('Expected: %s to exist.', filename)
        return -1

    try:
        lib = ctypes.cdll.LoadLibrary(filename)
    except:
        pydev_log.exception('Error loading: %s', filename)
        return -1

    if hasattr(sys, 'getswitchinterval'):
        get_interval, set_interval = sys.getswitchinterval, sys.setswitchinterval
    else:
        get_interval, set_interval = sys.getcheckinterval, sys.setcheckinterval

    prev_value = get_interval()
    ret = 0
    try:
        # Prevent going to any other thread... if we switch the thread during this operation we
        # could potentially corrupt the interpreter.
        set_interval(2 ** 15)

        set_trace_func = TracingFunctionHolder._original_tracing or sys.settrace

        if target_threads is None:
            target_threads = list(threading.enumerate())

        for t in target_threads:
            if t and not getattr(t, 'pydev_do_not_trace', None):
                show_debug_info = 0
                result = lib.AttachDebuggerTracing(ctypes.c_int(show_debug_info), ctypes.py_object(set_trace_func), ctypes.py_object(tracing_func), ctypes.c_uint(t.ident))
                if result != 0:
                    pydev_log.info('Unable to set tracing for existing threads. Result: %s', result)
                    ret = result
    finally:
        set_interval(prev_value)

    return ret

