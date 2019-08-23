# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import threading
import socket
from ptvsd.common import fmt, log, messaging
from tests.timeline import Request, Response


class CapturedOutput(object):
    """Captured stdout and stderr of the debugged process.
    """

    def __init__(self, session):
        self.session = session
        self._lock = threading.Lock()
        self._lines = {}
        self._worker_threads = []

    def __str__(self):
        return fmt("CapturedOutput({0})", self.session)

    def _worker(self, pipe, name):
        lines = self._lines[name]
        while True:
            try:
                line = pipe.readline()
            except Exception:
                line = None

            if line:
                log.info("{0} {1}> {2!r}", self.session, name, line)
                with self._lock:
                    lines.append(line)
            else:
                break

    def _capture(self, pipe, name):
        assert name not in self._lines
        self._lines[name] = []

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
        assert self.session.timeline.is_frozen

        try:
            result = self._lines[which]
        except KeyError:
            raise AssertionError(
                fmt("{0} was not captured for {1}", which, self.session)
            )

        # The list might still be appended to concurrently, so take a snapshot of it.
        with self._lock:
            result = list(result)

        if encoding is not None:
            result = [s.decode(encoding) for s in result]

        if not lines:
            sep = b"" if encoding is None else ""
            result = sep.join(result)

        return result

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


class BackChannel(object):
    TIMEOUT = 20

    def __init__(self, session):
        self.session = session
        self.port = None
        self._established = threading.Event()
        self._socket = None
        self._server_socket = None

    def __str__(self):
        return fmt("backchannel-{0}", self.session.id)

    def listen(self):
        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_socket.settimeout(self.TIMEOUT)
        self._server_socket.bind(('127.0.0.1', 0))
        _, self.port = self._server_socket.getsockname()
        self._server_socket.listen(0)

        def accept_worker():
            log.info('Listening for incoming connection from {0} on port {1}...', self, self.port)

            try:
                self._socket, _ = self._server_socket.accept()
            except socket.timeout:
                raise log.exception("Timed out waiting for {0} to connect", self)

            self._socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            log.info('Incoming connection from {0} accepted.', self)
            self._setup_stream()

        accept_thread = threading.Thread(
            target=accept_worker,
            name=fmt('{0} listener', self)
        )
        accept_thread.daemon = True
        accept_thread.start()

    def _setup_stream(self):
        self._stream = messaging.JsonIOStream.from_socket(self._socket, name=str(self))
        self._established.set()

    def receive(self):
        self._established.wait()
        return self._stream.read_json()

    def send(self, value):
        self.session.timeline.unfreeze()
        self._established.wait()
        t = self.session.timeline.mark(('sending', value))
        self._stream.write_json(value)
        return t

    def expect(self, expected):
        actual = self.receive()
        assert expected == actual, fmt(
            "Test expected {0!r} on backchannel, but got {1!r} from the debuggee",
            expected,
            actual,
        )

    def close(self):
        if self._socket:
            log.debug('Closing {0} socket of {1}...', self, self.session)
            try:
                self._socket.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            self._socket = None

        if self._server_socket:
            log.debug('Closing {0} server socket of {1}...', self, self.session)
            try:
                self._server_socket.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            self._server_socket = None


class ScratchPad(object):
    def __init__(self, session):
        self.session = session

    def __getitem__(self, key):
        raise NotImplementedError

    def __setitem__(self, key, value):
        """Sets debug_me.scratchpad[key] = value inside the debugged process.
        """

        stackTrace_responses = self.session.all_occurrences_of(
            Response(Request("stackTrace"))
        )
        assert stackTrace_responses, (
            'scratchpad requires at least one "stackTrace" request in the timeline.'
        )
        stack_trace = stackTrace_responses[-1].body
        frame_id = stack_trace["stackFrames"][0]["id"]

        log.info("{0} debug_me.scratchpad[{1!r}] = {2!r}", self.session, key, value)
        expr = fmt(
            "__import__('debug_me').scratchpad[{0!r}] = {1!r}",
            key,
            value,
        )
        self.session.request(
            "evaluate",
            {
                "frameId": frame_id,
                "context": "repl",
                "expression": expr,
            },
        )
