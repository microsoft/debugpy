# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, division, print_function, unicode_literals

import codecs
import os
import threading

from ptvsd.common import log
from ptvsd.launcher import adapter, debuggee


class CaptureOutput(object):
    """Captures output from the specified file descriptor, and tees it into another
    file descriptor while generating DAP "output" events for it.
    """

    instances = {}
    """Keys are output categories, values are CaptureOutput instances."""

    def __init__(self, category, fd, tee_fd, encoding):
        assert category not in self.instances
        self.instances[category] = self
        log.info("Capturing {0} of {1}.", category, debuggee.describe())

        self.category = category
        self._fd = fd
        self._tee_fd = tee_fd

        try:
            self._decoder = codecs.getincrementaldecoder(encoding)(errors="replace")
        except LookupError:
            self._decoder = None
            log.warning(
                'Unable to generate "output" events for {0} - unknown encoding {1!r}',
                category,
                encoding,
            )

        self._worker_thread = threading.Thread(target=self._worker, name=category)
        self._worker_thread.start()

    def __del__(self):
        fd = self._fd
        if fd is not None:
            try:
                os.close(fd)
            except Exception:
                pass

    def _send_output_event(self, s, final=False):
        if self._decoder is None:
            return

        s = self._decoder.decode(s, final=final)
        if len(s) == 0:
            return
        s = s.replace("\r\n", "\n")

        try:
            adapter.channel.send_event(
                "output", {"category": self.category, "output": s}
            )
        except Exception:
            pass  # channel to adapter is already closed

    def _worker(self):
        while self._fd is not None:
            try:
                s = os.read(self._fd, 0x1000)
            except Exception:
                break

            size = len(s)
            if size == 0:
                break

            # Tee the output first, before sending the "output" event.
            i = 0
            while i < size:
                written = os.write(self._tee_fd, s[i:])
                i += written
                if not written:
                    # This means that the output stream was closed from the other end.
                    # Do the same to the debuggee, so that it knows as well.
                    os.close(self._fd)
                    self._fd = None
                    break

            self._send_output_event(s)

        # Flush any remaining data in the incremental decoder.
        self._send_output_event(b"", final=True)


def wait_for_remaining_output():
    """Waits for all remaining output to be captured and propagated.
    """
    for category, instance in CaptureOutput.instances.items():
        log.info("Waiting for remaining {0} of {1}.", category, debuggee.describe())
        instance._worker_thread.join()
