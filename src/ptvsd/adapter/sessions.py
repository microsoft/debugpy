# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, division, print_function, unicode_literals

import contextlib
import itertools
import os
import threading
import time

from ptvsd.common import fmt, log, messaging, sockets, util
from ptvsd.adapter import components, launchers, servers


_lock = threading.RLock()
_sessions = set()
_sessions_changed = threading.Event()


class Session(util.Observable):
    """A debug session involving an IDE, an adapter, a launcher, and a debug server.

    The IDE and the adapter are always present, and at least one of launcher and debug
    server is present, depending on the scenario.
    """

    _counter = itertools.count(1)

    def __init__(self):
        from ptvsd.adapter import ide

        super(Session, self).__init__()

        self.lock = threading.RLock()
        self.id = next(self._counter)
        self._changed_condition = threading.Condition(self.lock)

        self.ide = components.missing(self, ide.IDE)
        """The IDE component. Always present."""

        self.launcher = components.missing(self, launchers.Launcher)
        """The launcher componet. Always present in "launch" sessions, and never
        present in "attach" sessions.
        """

        self.server = components.missing(self, servers.Server)
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

    def register(self):
        with _lock:
            _sessions.add(self)
            _sessions_changed.set()

    def notify_changed(self):
        with self:
            self._changed_condition.notify_all()

        # A session is considered ended once all components disconnect, and there
        # are no further incoming messages from anything to handle.
        components = self.ide, self.launcher, self.server
        if all(not com or not com.is_connected for com in components):
            with _lock:
                if self in _sessions:
                    log.info("{0} has ended.", self)
                    _sessions.remove(self)
                    _sessions_changed.set()

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

    def accept_connection_from_launcher(self, address=("127.0.0.1", 0)):
        return self._accept_connection_from(launchers.Launcher, address, timeout=10)

    def finalize(self, why, terminate_debuggee=None):
        """Finalizes the debug session.

        If the server is present, sends "disconnect" request with "terminateDebuggee"
        set as specified request to it; waits for it to disconnect, allowing any
        remaining messages from it to be handled; and closes the server channel.

        If the launcher is present, sends "terminate" request to it, regardless of the
        value of terminate; waits for it to disconnect, allowing any remaining messages
        from it to be handled; and closes the launcher channel.

        If the IDE is present, sends "terminated" event to it.

        If terminate_debuggee=None, it is treated as True if the session has a Launcher
        component, and False otherwise.
        """

        if self.is_finalizing:
            return
        self.is_finalizing = True
        log.info("{0}; finalizing {1}.", why, self)

        if terminate_debuggee is None:
            terminate_debuggee = bool(self.launcher)

        try:
            self._finalize(why, terminate_debuggee)
        except Exception:
            # Finalization should never fail, and if it does, the session is in an
            # indeterminate and likely unrecoverable state, so just fail fast.
            log.exception("Fatal error while finalizing {0}", self)
            os._exit(1)

        log.info("{0} finalized.", self)

    def _finalize(self, why, terminate_debuggee):
        # If the IDE started a session, and then disconnected before issuing "launch"
        # or "attach", the main thread will be blocked waiting for the first server
        # connection to come in - unblock it, so that we can exit.
        servers.dont_wait_for_first_connection()

        if self.server:
            if self.server.is_connected:
                try:
                    self.server.channel.request(
                        "disconnect", {"terminateDebuggee": terminate_debuggee}
                    )
                except Exception:
                    pass
            self.server.detach_from_session()

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

            # Wait until the launcher message queue fully drains. There is no timeout
            # here, because the final "terminated" event will only come after reading
            # user input in wait-on-exit scenarios.
            log.info("{0} waiting for {1} to disconnect...", self, self.launcher)
            self.wait_for(lambda: not self.launcher.is_connected)

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


def get(pid):
    with _lock:
        return next((session for session in _sessions if session.pid == pid), None)


def wait_until_ended():
    """Blocks until all sessions have ended.

    A session ends when all components that it manages disconnect from it.
    """
    while True:
        _sessions_changed.wait()
        with _lock:
            _sessions_changed.clear()
            if not len(_sessions):
                return
