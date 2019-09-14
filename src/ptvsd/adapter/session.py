# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import contextlib
import itertools
import os
import subprocess
import sys
import threading
import time

import ptvsd
import ptvsd.launcher
from ptvsd.common import (
    compat,
    fmt,
    log,
    messaging,
    options as common_options,
    sockets,
    util,
)
from ptvsd.adapter import components, ide, launcher, options as adapter_options, server


class Session(util.Observable):
    """A debug session involving an IDE, an adapter, a launcher, and a debug server.

    The IDE and the adapter are always present, and at least one of launcher and debug
    server is present, depending on the scenario.
    """

    _counter = itertools.count(1)

    def __init__(self):
        super(Session, self).__init__()

        self.lock = threading.RLock()
        self.id = next(self._counter)
        self._changed_condition = threading.Condition(self.lock)

        self.ide = components.missing(self, ide.IDE)
        """The IDE component. Always present."""

        self.launcher = components.missing(self, launcher.Launcher)
        """The launcher componet. Always present in "launch" sessions, and never
        present in "attach" sessions.
        """

        self.server = components.missing(self, server.Server)
        """The debug server component. Always present, unless this is a "launch"
        session with "noDebug".
        """

        self.no_debug = None
        """Whether this is a "noDebug" session."""

        self.pid = None
        """Process ID of the debuggee process."""

        self.debug_options = {}
        """Debug options as specified by "launch" or "attach" request."""

        self.is_finalizing = False
        """Whether finalize() has been invoked."""

        self.observers += [lambda *_: self.notify_changed()]

    def __str__(self):
        return fmt("Session-{0}", self.id)

    def __enter__(self):
        """Lock the session for exclusive access."""
        self.lock.acquire()
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        """Unlock the session."""
        self.lock.release()

    def wait_for_completion(self):
        self.ide.channel.wait()
        if self.launcher:
            self.launcher.channel.wait()
        if self.server:
            self.server.channel.wait()

    def notify_changed(self):
        with self:
            self._changed_condition.notify_all()

    def wait_for(self, predicate, timeout=None):
        """Waits until predicate() becomes true.

        The predicate is invoked with the session locked. If satisfied, the method
        returns immediately. Otherwise, the lock is released (even if it was held
        at entry), and the method blocks waiting for some attribute of either self,
        self.ide, self.server, or self.launcher to change. On every change, session
        is re-locked and predicate is re-evaluated, until it is satisfied.

        While the session is unlocked, message handlers for components other than
        the one that is waiting can run, but message handlers for that one are still
        blocked.

        If timeout is not None, the method will unblock and return after that many
        seconds regardless of whether the predicate was satisfied. The method returns
        False if it timed out, and True otherwise.
        """

        def wait_for_timeout():
            time.sleep(timeout)
            wait_for_timeout.timed_out = True
            self.notify_changed()

        wait_for_timeout.timed_out = False
        if timeout is not None:
            thread = threading.Thread(
                target=wait_for_timeout, name="Session.wait_for() timeout"
            )
            thread.daemon = True
            thread.start()

        with self:
            while not predicate():
                if wait_for_timeout.timed_out:
                    return False
                self._changed_condition.wait()
            return True

    def connect_to_ide(self):
        """Sets up a DAP message channel to the IDE over stdio.
        """

        log.info("{0} connecting to IDE over stdio...", self)
        stream = messaging.JsonIOStream.from_stdio()

        # Make sure that nothing else tries to interfere with the stdio streams
        # that are going to be used for DAP communication from now on.
        sys.stdout = sys.stderr
        sys.stdin = open(os.devnull, "r")

        ide.IDE(self, stream)

    def connect_to_server(self, address):
        """Sets up a DAP message channel to the server.

        The channel is established by connecting to the TCP socket listening on the
        specified address
        """

        host, port = address
        log.info("{0} connecting to Server on {1}:{2}...", self, host, port)
        sock = sockets.create_client()
        sock.connect(address)

        stream = messaging.JsonIOStream.from_socket(sock)
        server.Server(self, stream)

    @contextlib.contextmanager
    def _accept_connection_from(self, what, address, timeout=None):
        """Sets up a listening socket, accepts an incoming connection on it, sets
        up a message stream over that connection, and passes it on to what().

        Can be used in a with-statement to obtain the actual address of the listener
        socket before blocking on accept()::

            with accept_connection_from_server(...) as (host, port):
                # listen() returned - listening on (host, port) now
                ...
            # accept() returned - connection established
        """

        host, port = address
        listener = sockets.create_server(host, port, timeout)
        host, port = listener.getsockname()
        log.info(
            "{0} waiting for incoming connection from {1} on {2}:{3}...",
            self,
            what.__name__,
            host,
            port,
        )
        yield host, port

        try:
            sock, (other_host, other_port) = listener.accept()
        finally:
            listener.close()
        log.info(
            "{0} accepted incoming connection {1} from {2}:{3}.",
            self,
            what.__name__,
            other_host,
            other_port,
        )
        stream = messaging.JsonIOStream.from_socket(sock, what)
        what(self, stream)

    def accept_connection_from_ide(self, address):
        return self._accept_connection_from(ide.IDE, address)

    def accept_connection_from_server(self, address=("127.0.0.1", 0)):
        return self._accept_connection_from(server.Server, address, timeout=10)

    def _accept_connection_from_launcher(self, address=("127.0.0.1", 0)):
        return self._accept_connection_from(launcher.Launcher, address, timeout=10)

    def spawn_debuggee(self, request, sudo, args, console, console_title):
        cmdline = ["sudo"] if sudo else []
        cmdline += [sys.executable, os.path.dirname(ptvsd.launcher.__file__)]
        cmdline += args
        env = {str("PTVSD_SESSION_ID"): str(self.id)}

        def spawn_launcher():
            with self._accept_connection_from_launcher() as (_, launcher_port):
                env[str("PTVSD_LAUNCHER_PORT")] = str(launcher_port)
                if common_options.log_dir is not None:
                    env[str("PTVSD_LOG_DIR")] = compat.filename_str(
                        common_options.log_dir
                    )
                if adapter_options.log_stderr:
                    env[str("PTVSD_LOG_STDERR")] = str("debug info warning error")
                if console == "internalConsole":
                    # If we are talking to the IDE over stdio, sys.stdin and sys.stdout are
                    # redirected to avoid mangling the DAP message stream. Make sure the
                    # launcher also respects that.
                    subprocess.Popen(
                        cmdline,
                        env=dict(list(os.environ.items()) + list(env.items())),
                        stdin=sys.stdin,
                        stdout=sys.stdout,
                        stderr=sys.stderr,
                    )
                else:
                    self.ide.capabilities.require("supportsRunInTerminalRequest")
                    kinds = {
                        "integratedTerminal": "integrated",
                        "externalTerminal": "external",
                    }
                    self.ide.channel.request(
                        "runInTerminal",
                        {
                            "kind": kinds[console],
                            "title": console_title,
                            "args": cmdline,
                            "env": env,
                        },
                    )
            self.launcher.channel.delegate(request)

        if self.no_debug:
            spawn_launcher()
        else:
            with self.accept_connection_from_server() as (_, server_port):
                request.arguments["port"] = server_port
                spawn_launcher()
                # Don't accept connection from server until launcher sends us the
                # "process" event, to avoid a race condition between the launcher
                # and the server.
                if not self.wait_for(lambda: self.pid is not None, timeout=5):
                    raise request.cant_handle(
                        'Session timed out waiting for "process" event from {0}',
                        self.launcher,
                    )

    def inject_server(self, pid, ptvsd_args):
        with self.accept_connection_from_server() as (host, port):
            cmdline = [
                sys.executable,
                compat.filename(os.path.dirname(ptvsd.__file__)),
                "--client",
                "--host",
                host,
                "--port",
                str(port),
            ]
            cmdline += ptvsd_args
            cmdline += ["--pid", str(pid)]

            log.info(
                "{0} spawning attach-to-PID debugger injector: {1!r}", self, cmdline
            )

            try:
                subprocess.Popen(
                    cmdline,
                    bufsize=0,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
            except Exception as exc:
                log.exception("{0} failed to inject debugger", self)
                raise messaging.MessageHandlingError(
                    fmt("Failed to inject debugger: {0}", exc)
                )

    def finalize(self, why, terminate_debuggee=False):
        """Finalizes the debug session.

        If the server is present, sends "disconnect" request with "terminateDebuggee"
        set as specified) request to it; waits for it to disconnect, allowing any
        remaining messages from it to be handled; and closes the server channel.

        If the launcher is present, sends "terminate" request to it, regardless of the
        value of terminate; waits for it to disconnect, allowing any remaining messages
        from it to be handled; and closes the launcher channel.

        If the IDE is present, sends "terminated" event to it.
        """

        if self.is_finalizing:
            return
        self.is_finalizing = True
        log.info("{0}; finalizing {1}.", why, self)

        try:
            self._finalize(why, terminate_debuggee)
        except Exception:
            # Finalization should never fail, and if it does, the session is in an
            # indeterminate and likely unrecoverable state, so just fail fast.
            log.exception("Fatal error while finalizing {0}", self)
            os._exit(1)

        log.info("{0} finalized.", self)

    def _finalize(self, why, terminate_debuggee):
        if self.server and self.server.is_connected:
            try:
                self.server.channel.request(
                    "disconnect", {"terminateDebuggee": terminate_debuggee}
                )
            except Exception:
                pass

            try:
                self.server.channel.close()
            except Exception:
                log.exception()

            # Wait until the server message queue fully drains - there won't be any
            # more events after close(), but there may still be pending responses.
            log.info("{0} waiting for {1} to disconnect...", self, self.server)
            if not self.wait_for(lambda: not self.server.is_connected, timeout=5):
                log.warning(
                    "{0} timed out waiting for {1} to disconnect.", self, self.server
                )

        if self.launcher and self.launcher.is_connected:
            # If there was a server, we just disconnected from it above, which should
            # cause the debuggee process to exit - so let's wait for that first.
            if self.server:
                log.info('{0} waiting for "exited" event...', self)
                if not self.wait_for(
                    lambda: self.launcher.exit_code is not None, timeout=5
                ):
                    log.warning('{0} timed out waiting for "exited" event.', self)

            # Terminate the debuggee process if it's still alive for any reason -
            # whether it's because there was no server to handle graceful shutdown,
            # or because the server couldn't handle it for some reason.
            try:
                self.launcher.channel.request("terminate")
            except Exception:
                pass

            # Wait until the launcher message queue fully drains.
            log.info("{0} waiting for {1} to disconnect...", self, self.launcher)
            if not self.wait_for(lambda: not self.launcher.is_connected, timeout=5):
                log.warning(
                    "{0} timed out waiting for {1} to disconnect.", self, self.launcher
                )

            try:
                self.launcher.channel.close()
            except Exception:
                log.exception()

        # Tell the IDE that debugging is over, but don't close the channel until it
        # tells us to, via the "disconnect" request.
        if self.ide and self.ide.is_connected:
            try:
                self.ide.channel.send_event("terminated")
            except Exception:
                pass
