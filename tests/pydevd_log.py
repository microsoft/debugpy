# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import os

from ptvsd.common import log, compat
from _pydev_bundle import pydev_log


def enable(filename):
    os.environ[str("PYDEVD_DEBUG")] = str("True")
    os.environ[str("PYDEVD_DEBUG_FILE")] = compat.filename_str(filename)
    log.debug("pydevd log will be at {0}", filename)


def dump(why):
    assert why

    pydevd_debug_file = os.environ.get("PYDEVD_DEBUG_FILE")
    if not pydevd_debug_file:
        return

    log_contents = []
    try:
        for filename in pydev_log.list_log_files(pydevd_debug_file):
            with open(filename) as stream:
                log_contents.append("---------- %s ------------\n\n" % (filename,))
                log_contents.append(stream.read())
    except Exception:
        log.exception(
            "Test {0}, but pydevd log {1} could not be retrieved.",
            why,
            pydevd_debug_file,
        )
        return

    log.info("Test {0}; pydevd log:\n\n{1}", why, "".join(log_contents))
