# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

"""Python 2/3 compatibility helpers.
"""

import inspect
import sys

from ptvsd.common import fmt


try:
    import builtins
except ImportError:
    import __builtin__ as builtins # noqa

try:
    import queue
except ImportError:
    import Queue as queue # noqa

try:
    unicode = builtins.unicode
    bytes = builtins.str
except AttributeError:
    unicode = builtins.str
    bytes = builtins.bytes

try:
    xrange = builtins.xrange
except AttributeError:
    xrange = builtins.range


def force_unicode(s, encoding, errors="strict"):
    """Converts s to Unicode, using the provided encoding. If s is already Unicode,
    it is returned as is.
    """
    return s.decode(encoding, errors) if isinstance(s, bytes) else s


def maybe_utf8(s, errors="strict"):
    """Converts s to Unicode, assuming it is UTF-8. If s is already Unicode, it is
    returned as is
    """
    return force_unicode(s, "utf-8", errors)


def filename(s, errors="strict"):
    """Ensures that filename is Unicode.
    """
    return force_unicode(s, sys.getfilesystemencoding(), errors)


def nameof(obj, quote=False):
    """Returns the most descriptive name of a Python module, class, or function,
    as a Unicode string.

    If quote=True, name is quoted with repr().
    """

    try:
        name = obj.__qualname__
    except AttributeError:
        try:
            name = obj.__name__
        except AttributeError:
            # Fall back to raw repr(), and skip quoting.
            try:
                return maybe_utf8(repr(obj), "replace")
            except Exception:
                return "<unknown>"

    if quote:
        name = repr(name)
    return maybe_utf8(name, "replace")


def srcnameof(obj):
    """Returns the most descriptive name of a Python module, class, or function,
    including source information (filename and linenumber), if available.
    """

    name = nameof(obj, quote=True)

    # Get the source information if possible.
    try:
        src_file = filename(inspect.getsourcefile(obj), "replace")
    except Exception:
        pass
    else:
        name += fmt(" (file {0!r}", src_file)
        try:
            _, src_lineno = inspect.getsourcelines(obj)
        except Exception:
            pass
        else:
            name += fmt(", line {0}", src_lineno)
        name += ")"

    return name
