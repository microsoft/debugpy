import contextlib
import sys
import threading

from ptvsd import wrapper
from ptvsd.socket import (
    close_socket, create_server, create_client, connect, Address)
from .exit_handlers import (
    ExitHandlers, UnsupportedSignalError,
    kill_current_proc)
from .session import DebugSession
from ._util import ignore_errors, debug


def _wait_on_exit():
    if sys.__stdout__ is not None:
        try:
            import msvcrt
        except ImportError:
            sys.__stdout__.write('Press Enter to continue . . . ')
            sys.__stdout__.flush()
            sys.__stdin__.read(1)
        else:
            sys.__stdout__.write('Press any key to continue . . . ')
            sys.__stdout__.flush()
            msvcrt.getch()


class DaemonError(RuntimeError):
    """Indicates that a Daemon had a problem."""
    MSG = 'error'

    def __init__(self, msg=None):
        if msg is None:
            msg = self.MSG
        super(DaemonError, self).__init__(msg)


class DaemonClosedError(DaemonError):
    """Indicates that a Daemon was unexpectedly closed."""
    MSG = 'closed'


class DaemonStoppedError(DaemonError):
    """Indicates that a Daemon was unexpectedly stopped."""
    MSG = 'stopped'


# TODO: Inherit from Closeable.
# TODO: Inherit from Startable?

class Daemon(object):
    """The process-level manager for the VSC protocol debug adapter."""

    exitcode = 0

    def __init__(self, wait_on_exit=_wait_on_exit,
                 addhandlers=True, killonclose=True,
                 hidebadsessions=True):
        self.wait_on_exit = wait_on_exit
        self.killonclose = killonclose
        self.hidebadsessions = hidebadsessions

        self._closed = False
        self._exiting_via_atexit_handler = False

        self._pydevd = None
        self._server = None
        self._numstarts = 0

        self._session = None
        self._sessionlock = None
        self._numsessions = 0

        self._exithandlers = ExitHandlers()
        if addhandlers:
            self.install_exit_handlers()

    @property
    def pydevd(self):
        return self._pydevd

    @property
    def session(self):
        """The current session."""
        return self._session

    def install_exit_handlers(self):
        """Set the placeholder handlers."""
        self._exithandlers.install()

        try:
            self._exithandlers.add_atexit_handler(self._handle_atexit)
        except ValueError:
            pass
        for signum in self._exithandlers.SIGNALS:
            try:
                self._exithandlers.add_signal_handler(signum,
                                                      self._handle_signal)
            except ValueError:
                # Already added.
                pass
            except UnsupportedSignalError:
                # TODO: This shouldn't happen.
                pass

    @contextlib.contextmanager
    def started(self, stoponcmexit=True):
        """A context manager that starts the daemon.

        If there's a failure then the daemon is stopped.  It is also
        stopped at the end of the with block if "stoponcmexit" is True
        (the default).
        """
        pydevd = self.start()
        try:
            yield pydevd
        except Exception:
            self._stop_quietly()
            raise
        else:
            if stoponcmexit:
                self._stop_quietly()

    def is_running(self):
        """Return True if the daemon is running."""
        if self._pydevd is None:
            return False
        return True

    def start(self):
        """Return the "socket" to use for pydevd after setting it up."""
        if self._closed:
            raise DaemonClosedError()
        if self._pydevd is not None:
            raise RuntimeError('already started')

        return self._start()

    def stop(self):
        """Un-start the daemon (i.e. stop the "socket")."""
        if self._closed:
            raise DaemonClosedError()
        if self._pydevd is None:
            raise RuntimeError('not started')

        self._stop()

    def start_server(self, addr):
        """Return (pydevd "socket", next_session) with a new server socket."""
        addr = Address.from_raw(addr)
        with self.started(stoponcmexit=False) as pydevd:
            assert self._sessionlock is None
            assert self._session is None
            self._server = create_server(addr.host, addr.port)
            self._sessionlock = threading.Lock()

        def next_session(**kwargs):
            if self._closed:
                raise DaemonClosedError()
            server = self._server
            if self._pydevd is None or server is None:
                raise DaemonStoppedError()
            sessionlock = self._sessionlock
            if sessionlock is None:
                raise DaemonStoppedError()

            debug('getting next session')
            sessionlock.acquire()  # Released in _handle_session_closing().
            debug('session lock acquired')
            if self._closed:
                raise DaemonClosedError()
            if self._pydevd is None or self._server is None:
                raise DaemonStoppedError()
            timeout = kwargs.pop('timeout', None)
            try:
                debug('getting session socket')
                client = connect(server, None, **kwargs)
                session = DebugSession.from_raw(
                    client,
                    notify_closing=self._handle_session_closing,
                    ownsock=True,
                )
                debug('starting session')
                self._start_session(session, 'ptvsd.Server', timeout)
                debug('session started')
                return session
            except Exception as exc:
                debug('session exc:', exc, tb=True)
                with ignore_errors():
                    self._stop_session()
                if self.hidebadsessions:
                    debug('hiding bad session')
                    # TODO: Log the error?
                    return None
                self._stop_quietly()
                raise

        return pydevd, next_session

    def start_client(self, addr):
        """Return (pydevd "socket", start_session) with a new client socket."""
        addr = Address.from_raw(addr)
        with self.started(stoponcmexit=False) as pydevd:
            assert self._session is None
            client = create_client()
            connect(client, addr)

        def start_session():
            if self._closed:
                raise DaemonClosedError()
            if self._pydevd is None:
                raise DaemonStoppedError()
            if self._session is not None:
                raise RuntimeError('session already started')
            if self._numsessions:
                raise RuntimeError('session stopped')

            try:
                session = DebugSession.from_raw(
                    client,
                    notify_closing=self._handle_session_closing,
                    ownsock=True,
                )
                self._start_session(session, 'ptvsd.Client', None)
                return session
            except Exception:
                self._stop_quietly()
                raise

        return pydevd, start_session

    def start_session(self, session, threadname, timeout=None):
        """Start the debug session and remember it.

        If "session" is a client socket then a session is created
        from it.
        """
        if self._closed:
            raise DaemonClosedError()
        if self._pydevd is None:
            raise RuntimeError('not started yet')
        if self._server is not None:
            raise RuntimeError('running as server')
        if self._session is not None:
            raise RuntimeError('session already started')

        session = DebugSession.from_raw(
            session,
            notify_closing=self._handle_session_closing,
            ownsock=True,
        )
        self._start_session(session, threadname, timeout)
        return session

    def close(self):
        """Stop all loops and release all resources."""
        if self._closed:
            raise DaemonClosedError('already closed')

        self._close()

    def re_build_breakpoints(self):
        """Restore the breakpoints to their last values."""
        if self._session is None:
            return
        return self._session.re_build_breakpoints()

    # internal methods

    def _close(self):
        self._closed = True
        session = self._stop()
        if session is not None:
            normal, abnormal = session.wait_options()
            if (normal and not self.exitcode) or (abnormal and self.exitcode):
                self.wait_on_exit()

    def _start(self):
        self._numstarts += 1
        self._pydevd = wrapper.PydevdSocket(
            self._handle_pydevd_message,
            self._handle_pydevd_close,
            self._getpeername,
            self._getsockname,
        )
        return self._pydevd

    def _stop(self):
        sessionlock = self._sessionlock
        self._sessionlock = None
        server = self._server
        self._server = None
        pydevd = self._pydevd
        self._pydevd = None

        session = self._session
        with ignore_errors():
            self._stop_session()

        if sessionlock is not None:
            try:
                sessionlock.release()
            except Exception:
                pass

        if server is not None:
            with ignore_errors():
                close_socket(server)

        if pydevd is not None:
            with ignore_errors():
                close_socket(pydevd)

        return session

    def _stop_quietly(self):
        if self._closed:
            return
        with ignore_errors():
            self._stop()

    def _start_session(self, session, threadname, timeout):
        self._session = session
        self._numsessions += 1
        try:
            session.start(
                threadname,
                self._pydevd.pydevd_notify,
                self._pydevd.pydevd_request,
                timeout=timeout,
            )
        except Exception:
            assert self._session is session
            with ignore_errors():
                self._stop_session()
            raise

    def _stop_session(self):
        session = self._session
        self._session = None

        try:
            if session is not None:
                session.stop(self.exitcode if self._server is None else None)
                session.close()
        finally:
            sessionlock = self._sessionlock
            if sessionlock is not None:
                try:
                    sessionlock.release()
                except Exception:  # TODO: Make it more specific?
                    debug('session lock not released')
                else:
                    debug('session lock released')
        debug('session stopped')

    def _handle_atexit(self):
        self._exiting_via_atexit_handler = True
        if not self._closed:
            self._close()
        # TODO: Is this broken (due to always clearing self._session on close?
        if self._session is not None:
            self._session.wait_until_stopped()

    def _handle_signal(self, signum, frame):
        if not self._closed:
            self._close()
        sys.exit(0)

    def _handle_session_closing(self, kill=False):
        debug('handling closing session')
        if self._server is not None and not kill:
            self._session = None
            self._stop_session()
            return

        if not self._closed:
            self._close()
        if kill and self.killonclose and not self._exiting_via_atexit_handler:
            kill_current_proc()

    # internal methods for PyDevdSocket().

    def _handle_pydevd_message(self, cmdid, seq, text):
        if self._session is None:
            # TODO: Do more than ignore?
            return
        self._session.handle_pydevd_message(cmdid, seq, text)

    def _handle_pydevd_close(self):
        if self._closed:
            return
        self._close()

    def _getpeername(self):
        if self._session is None:
            raise NotImplementedError
        return self._session.socket.getpeername()

    def _getsockname(self):
        if self._session is None:
            raise NotImplementedError
        return self._session.socket.getsockname()
