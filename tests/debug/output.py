# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import os
import re
import threading

from debugpy.common import log


class CapturedOutput(object):
    """Captures stdout and stderr of the debugged process."""

    def __init__(self, session, **fds):
        self.session = session
        self._lock = threading.Lock()
        self._chunks = {}
        self._worker_threads = []

        for stream_name, fd in fds.items():
            log.info("Capturing {0} {1}", session.debuggee_id, stream_name)
            self._capture(fd, stream_name)

    def __str__(self):
        return f"CapturedOutput[{self.session.id}]"

    def _worker(self, fd, name):
        chunks = self._chunks[name]
        try:
            while True:
                try:
                    chunk = os.read(fd, 0x1000)
                except Exception:
                    break
                if not len(chunk):
                    break

                lines = "\n".join(
                    repr(line) for line, _ in re.findall(b"(.+?(\n|$))", chunk)
                )
                log.info("{0} {1}:\n{2}", self.session.debuggee_id, name, lines)

                with self._lock:
                    chunks.append(chunk)
        finally:
            os.close(fd)

    def _capture(self, fd, name):
        assert name not in self._chunks
        self._chunks[name] = []

        thread = threading.Thread(
            target=lambda: self._worker(fd, name), name=f"{self} {name}"
        )
        thread.daemon = True
        thread.start()
        self._worker_threads.append(thread)

    def wait(self, timeout=None):
        """Wait for all remaining output to be captured."""
        if not self._worker_threads:
            return
        log.debug("Waiting for remaining {0} output...", self.session.debuggee_id)
        for t in self._worker_threads:
            t.join(timeout)
        self._worker_threads[:] = []

    def _output(self, which, encoding, lines):
        try:
            result = self._chunks[which]
        except KeyError:
            raise AssertionError(
                f"{which} was not captured for {self.session.debuggee_id}"
            )

        with self._lock:
            result = b"".join(result)
        if encoding is not None:
            result = result.decode(encoding)

        return result.splitlines() if lines else result

    def stdout(self, encoding=None):
        """Returns stdout captured from the debugged process, as a single string.

        If encoding is None, returns bytes. Otherwise, returns str.
        """
        return self._output("stdout", encoding, lines=False)

    def stderr(self, encoding=None):
        """Returns stderr captured from the debugged process, as a single string.

        If encoding is None, returns bytes. Otherwise, returns str.
        """
        return self._output("stderr", encoding, lines=False)

    def stdout_lines(self, encoding=None):
        """Returns stdout captured from the debugged process, as a list of lines.

        If encoding is None, each line is bytes. Otherwise, each line is str.
        """
        return self._output("stdout", encoding, lines=True)

    def stderr_lines(self, encoding=None):
        """Returns stderr captured from the debugged process, as a list of lines.

        If encoding is None, each line is bytes. Otherwise, each line is str.
        """
        return self._output("stderr", encoding, lines=True)
