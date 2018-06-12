# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import pydevd
import sys
import time
import threading
import traceback

from ptvsd.daemon import DaemonBase
from ptvsd.session import DebugSession
from ptvsd.wrapper import (
    WAIT_FOR_THREAD_FINISH_TIMEOUT, VSCLifecycleMsgProcessor)
from pydevd import init_stdout_redirect, init_stderr_redirect


HOSTNAME = 'localhost'
OUTPUT_POLL_PERIOD = 0.3


def run(address, filename, is_module, *args, **kwargs):
    # TODO: docstring
    # TODO: client/server -> address
    daemon = Daemon()
    if not daemon.wait_for_launch(address):
        return

    debugger = pydevd.PyDB()
    # We do not want some internal methods to get executed in non-debug mode.
    debugger.init_matplotlib_support = lambda *arg: None
    debugger.run(
        file=filename,
        globals=None,
        locals=None,
        is_module=is_module,
        set_trace=False)
    # Wait for some time (a little longer than output redirection polling).
    # This is necessary to ensure all output is captured and redirected.
    time.sleep(OUTPUT_POLL_PERIOD + 0.1)


class OutputRedirection(object):
    # TODO: docstring

    def __init__(self, on_output=lambda category, output: None):
        self._on_output = on_output
        self._stopped = False
        self._thread = None

    def start(self):
        # TODO: docstring
        init_stdout_redirect()
        init_stderr_redirect()
        self._thread = threading.Thread(
            target=self._run, name='ptvsd.output.redirection')
        self._thread.pydev_do_not_trace = True
        self._thread.is_pydev_daemon_thread = True
        self._thread.daemon = True
        self._thread.start()

    def stop(self):
        # TODO: docstring
        if self._stopped:
            return

        self._stopped = True
        self._thread.join(WAIT_FOR_THREAD_FINISH_TIMEOUT)

    def _run(self):
        while not self._stopped:
            self._check_output(sys.stdoutBuf, 'stdout')
            self._check_output(sys.stderrBuf, 'stderr')
            time.sleep(OUTPUT_POLL_PERIOD)

    def _check_output(self, out, category):
        '''Checks the output to see if we have to send some buffered,
        output to the debug server

        @param out: sys.stdout or sys.stderr
        @param category: stdout or stderr
        '''

        try:
            v = out.getvalue()

            if v:
                self._on_output(category, v)
        except Exception:
            traceback.print_exc()


class Daemon(DaemonBase):
    """The process-level manager for the VSC protocol debug adapter."""

    LAUNCH_TIMEOUT = 10000  # seconds

    class SESSION(DebugSession):
        class MESSAGE_PROCESSOR(VSCLifecycleMsgProcessor):
            def on_invalid_request(self, request, args):
                self.send_response(request, success=True)

    def wait_for_launch(self, addr, timeout=LAUNCH_TIMEOUT):
        # TODO: docstring
        launched = threading.Event()
        _, start_session = self.start_client(addr)
        start_session(
            notify_launch=launched.set,
        )
        return launched.wait(timeout)

    def _start(self):
        self._output_monitor = OutputRedirection(self._send_output)
        self._output_monitor.start()
        return NoSocket()

    def _close(self):
        self._output_monitor.stop()
        super(Daemon, self)._close()

    def _send_output(self, category, output):
        if self.session is None:
            return
        self.session._msgprocessor.send_event('output',
                                              category=category,
                                              output=output)


class NoSocket(object):
    """A object with a noop socket lifecycle."""

    def shutdown(self, *args, **kwargs):
        pass

    def close(self):
        pass
