# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import io
import os
import shutil
import sys

from debugpy.common import json, log


def write_title(title, stream=None, sep="~"):
    """Write a section title.
    If *stream* is None sys.stderr will be used, *sep* is used to
    draw the line.
    """
    if stream is None:
        stream = sys.stderr
    width, height = shutil.get_terminal_size()
    fill = int((width - len(title) - 2) / 2)
    line = " ".join([sep * fill, title, sep * fill])
    if len(line) < width:
        line += sep * (width - len(line))
    stream.write("\n" + line + "\n")

def dump():
    if log.log_dir is None:
        return
    log.info("Dumping logs from {0}", json.repr(log.log_dir))

    for dirpath, dirnames, filenames in os.walk(log.log_dir):
        for name in sorted(filenames):
            if not name.startswith("debugpy") and not name.startswith("pydevd"):
                continue
            try:
                path = os.path.join(dirpath, name)
                with io.open(path, encoding="utf-8", errors="backslashreplace") as f:
                    s = f.read()
            except Exception:
                pass
            else:
                path = os.path.relpath(path, log.log_dir)
                write_title(path)
                print(s, file=sys.stderr)
