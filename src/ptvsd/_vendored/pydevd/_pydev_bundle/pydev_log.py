from _pydevd_bundle.pydevd_constants import DebugInfoHolder
from _pydev_imps._pydev_saved_modules import threading
from contextlib import contextmanager
import traceback
currentThread = threading.currentThread

WARN_ONCE_MAP = {}


@contextmanager
def log_context(trace_level, stream):
    '''
    To be used to temporarily change the logging settings.
    '''
    original_trace_level = DebugInfoHolder.DEBUG_TRACE_LEVEL
    original_stream = DebugInfoHolder.DEBUG_STREAM

    DebugInfoHolder.DEBUG_TRACE_LEVEL = trace_level
    DebugInfoHolder.DEBUG_STREAM = stream
    try:
        yield
    finally:
        DebugInfoHolder.DEBUG_TRACE_LEVEL = original_trace_level
        DebugInfoHolder.DEBUG_STREAM = original_stream


def _pydevd_log(level, msg, *args):
    '''
    Levels are:

    0 most serious warnings/errors (always printed)
    1 warnings/significant events
    2 informational trace
    3 verbose mode
    '''
    if level <= DebugInfoHolder.DEBUG_TRACE_LEVEL:
        # yes, we can have errors printing if the console of the program has been finished (and we're still trying to print something)
        try:
            try:
                if args:
                    msg = msg % args
            except:
                msg = '%s - %s' % (msg, args)
            DebugInfoHolder.DEBUG_STREAM.write('%s\n' % (msg,))
            DebugInfoHolder.DEBUG_STREAM.flush()
        except:
            pass
        return True


def _pydevd_log_exception(msg='', *args):
    if msg or args:
        _pydevd_log(0, msg, *args)
    try:
        traceback.print_exc(file=DebugInfoHolder.DEBUG_STREAM)
        DebugInfoHolder.DEBUG_STREAM.flush()
    except:
        raise


def verbose(msg, *args):
    if DebugInfoHolder.DEBUG_TRACE_LEVEL >= 3:
        _pydevd_log(3, msg, *args)


def debug(msg, *args):
    if DebugInfoHolder.DEBUG_TRACE_LEVEL >= 2:
        _pydevd_log(2, msg, *args)


def info(msg, *args):
    if DebugInfoHolder.DEBUG_TRACE_LEVEL >= 1:
        _pydevd_log(1, msg, *args)


warn = info


def critical(msg, *args):
    _pydevd_log(0, msg, *args)


def exception(msg='', *args):
    try:
        _pydevd_log_exception(msg, *args)
    except:
        pass  # Should never fail (even at interpreter shutdown).


error = exception


def error_once(msg, *args):
    message = msg % args
    if message not in WARN_ONCE_MAP:
        WARN_ONCE_MAP[message] = True
        critical(message)

