# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, absolute_import, unicode_literals

import contextlib
import functools
import io
import platform
import os
import sys
import threading
import traceback

import ptvsd
from ptvsd.common import compat, fmt, options, timestamp


LEVELS = ("debug", "info", "warning", "error")
"""Logging levels, lowest to highest importance.
"""

stderr = sys.__stderr__

stderr_levels = {"warning", "error"}
"""What should be logged to stderr.
"""

file_levels = set(LEVELS)
"""What should be logged to file, when it is not None.
"""

file = None
"""If not None, which file to log to.

This can be automatically set by to_file().
"""

timestamp_format = "09.3f"
"""Format spec used for timestamps. Can be changed to dial precision up or down.
"""


_lock = threading.Lock()
_tls = threading.local()


# Used to inject a newline into stderr if logging there, to clean up the output
# when it's intermixed with regular prints from other sources.
def newline(level="info"):
    with _lock:
        if level in stderr_levels:
            try:
                stderr.write("\n")
            except Exception:
                pass


def write(level, text):
    assert level in LEVELS

    t = timestamp.current()
    format_string = "{0}+{1:" + timestamp_format + "}: "
    prefix = fmt(format_string, level[0].upper(), t)

    indent = "\n" + (" " * len(prefix))
    output = indent.join(text.split("\n"))

    if current_handler():
        prefix += "(while handling {}){}".format(current_handler(), indent)

    output = prefix + output + "\n\n"

    with _lock:
        if level in stderr_levels:
            try:
                stderr.write(output)
            except Exception:
                pass

        if file and level in file_levels:
            try:
                file.write(output)
                file.flush()
            except Exception:
                pass

    return text


def write_format(level, format_string, *args, **kwargs):
    try:
        text = fmt(format_string, *args, **kwargs)
    except Exception:
        exception()
        raise
    return write(level, text)


debug = functools.partial(write_format, "debug")
info = functools.partial(write_format, "info")
warning = functools.partial(write_format, "warning")


def error(*args, **kwargs):
    """Logs an error.

    Returns the output wrapped in AssertionError. Thus, the following::

        raise log.error(...)

    has the same effect as::

        log.error(...)
        assert False, fmt(...)
    """
    return AssertionError(write_format("error", *args, **kwargs))


def stack(title="Stack trace"):
    stack = "\n".join(traceback.format_stack())
    debug("{0}:\n\n{1}", title, stack)


def exception(format_string="", *args, **kwargs):
    """Logs an exception with full traceback.

    If format_string is specified, it is formatted with fmt(*args, **kwargs), and
    prepended to the exception traceback on a separate line.

    If exc_info is specified, the exception it describes will be logged. Otherwise,
    sys.exc_info() - i.e. the exception being handled currently - will be logged.

    If level is specified, the exception will be logged as a message of that level.
    The default is "error".

    Returns the exception object, for convenient re-raising::

        try:
            ...
        except Exception:
            raise log.exception()  # log it and re-raise
    """

    level = kwargs.pop("level", "error")
    exc_info = kwargs.pop("exc_info", sys.exc_info())

    if format_string:
        format_string += "\n\n"
    format_string += "{exception}"

    exception = "".join(traceback.format_exception(*exc_info))
    write_format(level, format_string, *args, exception=exception, **kwargs)

    return exc_info[1]


def escaped_exceptions(f):
    def g(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception:
            # Must not use try/except here to avoid overwriting the caught exception.
            exception("Exception escaped from {0}", compat.srcnameof(f))
            raise

    return g


def to_file(filename=None):
    # TODO: warn when options.log_dir is unset, after fixing improper use in ptvsd.server
    global file
    if file is not None or options.log_dir is None:
        return

    if filename is None:
        if options.log_dir is None:
            warning(
                "ptvsd.to_file() cannot generate log file name - ptvsd.options.log_dir is not set"
            )
            return
        filename = fmt("{0}/ptvsd-{1}.log", options.log_dir, os.getpid())

    file = io.open(filename, "w", encoding="utf-8")

    info(
        "{0} {1}\n{2} {3} ({4}-bit)\nptvsd {5}",
        platform.platform(),
        platform.machine(),
        platform.python_implementation(),
        platform.python_version(),
        64 if sys.maxsize > 2 ** 32 else 32,
        ptvsd.__version__,
    )


def current_handler():
    try:
        return _tls.current_handler
    except AttributeError:
        _tls.current_handler = None
        return None


@contextlib.contextmanager
def handling(what):
    assert current_handler() is None, fmt(
        "Can't handle {0} - already handling {1}", what, current_handler()
    )
    _tls.current_handler = what
    try:
        yield
    finally:
        _tls.current_handler = None


@contextlib.contextmanager
def suspend_handling():
    what = current_handler()
    _tls.current_handler = None
    try:
        yield
    finally:
        _tls.current_handler = what
