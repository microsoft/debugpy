# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, division, print_function, unicode_literals

import threading

from ptvsd.common import fmt, log


class CaptureOutput(object):
    """Captures stdout and stderr of the debugged process.
    """

    def __init__(self, session):
        self.session = session
        self._lock = threading.Lock()
        self._chunks = {}
        self._worker_threads = []

    def __str__(self):
        return fmt("CaptureOutput({0})", self.session)

    def _worker(self, pipe, name):
        chunks = self._chunks[name]
        while True:
            try:
                chunk = pipe.read(0x1000)
            except Exception:
                break
            if not len(chunk):
                break

            log.info("{0} {1}> {2!r}", self.session, name, chunk)
            with self._lock:
                chunks.append(chunk)

    def _capture(self, pipe, name):
        assert name not in self._chunks
        self._chunks[name] = []

        thread = threading.Thread(
            target=lambda: self._worker(pipe, name), name=fmt("{0} {1}", self, name)
        )
        thread.daemon = True
        thread.start()
        self._worker_threads.append(thread)

    def capture(self, process):
        """Start capturing stdout and stderr of the process.
        """
        assert not self._worker_threads
        log.info("Capturing {0} stdout and stderr", self.session)
        self._capture(process.stdout, "stdout")
        self._capture(process.stderr, "stderr")

    def wait(self, timeout=None):
        """Wait for all remaining output to be captured.
        """
        if not self._worker_threads:
            return
        log.debug("Waiting for remaining {0} stdout and stderr...", self.session)
        for t in self._worker_threads:
            t.join(timeout)
        self._worker_threads[:] = []

    def _output(self, which, encoding, lines):
        try:
            result = self._chunks[which]
        except KeyError:
            raise AssertionError(
                fmt("{0} was not captured for {1}", which, self.session)
            )

        with self._lock:
            result = b"".join(result)
        if encoding is not None:
            result = result.decode(encoding)

        return result.splitlines() if lines else result

    def stdout(self, encoding=None):
        """Returns stdout captured from the debugged process, as a single string.

        If encoding is None, returns bytes. Otherwise, returns unicode.
        """
        return self._output("stdout", encoding, lines=False)

    def stderr(self, encoding=None):
        """Returns stderr captured from the debugged process, as a single string.

        If encoding is None, returns bytes. Otherwise, returns unicode.
        """
        return self._output("stderr", encoding, lines=False)

    def stdout_lines(self, encoding=None):
        """Returns stdout captured from the debugged process, as a list of lines.

        If encoding is None, each line is bytes. Otherwise, each line is unicode.
        """
        return self._output("stdout", encoding, lines=True)

    def stderr_lines(self, encoding=None):
        """Returns stderr captured from the debugged process, as a list of lines.

        If encoding is None, each line is bytes. Otherwise, each line is unicode.
        """
        return self._output("stderr", encoding, lines=True)
