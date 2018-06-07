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


def _wait_for_user():
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

    def __init__(self, wait_for_user=_wait_for_user,
                 addhandlers=True, killonclose=True,
                 singlesession=False):

        self._started = False
        self._closed = False

        self._pydevd = None  # set when started

        # session-related

        self._singlesession = singlesession

        self._server = None
        self._session = None
        self._numsessions = 0
        self._sessionlock = None

        # proc-related

        self._wait_for_user = wait_for_user
        self._killonclose = killonclose

        self._exiting_via_atexit_handler = False
        self._wait_on_exit = (lambda ec: False)

        self._exithandlers = ExitHandlers()
        if addhandlers:
            self._install_exit_handlers()

    @property
    def pydevd(self):
        return self._pydevd

    @property
    def session(self):
        """The current session."""
        return self._session

    @contextlib.contextmanager
    def started(self):
        """A context manager that starts the daemon and stops it for errors."""
        self.start()
        try:
            yield self
        except Exception:
            self._stop_quietly()
            raise

    @contextlib.contextmanager
    def running(self):
        """A context manager that starts the daemon.

        If there's a failure then the daemon is stopped.  It is also
        stopped at the end of the with block.
        """
        self.start()
        try:
            yield self
        finally:
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
        if self._started:
            raise RuntimeError('already started')
        self._started = True

        return self._start()

    def start_server(self, addr, hidebadsessions=True):
        """Return (pydevd "socket", next_session) with a new server socket."""
        addr = Address.from_raw(addr)
        with self.started():
            assert self._sessionlock is None
            assert self.session is None
            self._server = create_server(addr.host, addr.port)
            self._sessionlock = threading.Lock()
        pydevd = self._pydevd

        def check_ready():
            self._check_ready_for_session()
            if self._server is None:
                raise DaemonStoppedError()

        def next_session(**kwargs):
            server = self._server
            sessionlock = self._sessionlock
            check_ready()

            debug('getting next session')
            sessionlock.acquire()  # Released in _finish_session().
            debug('session lock acquired')
            # It may have closed or stopped while we waited.
            check_ready()

            timeout = kwargs.pop('timeout', None)
            try:
                debug('getting session socket')
                client = connect(server, None, **kwargs)
                self._bind_session(client)
                debug('starting session')
                self._start_session('ptvsd.Server', timeout)
                debug('session started')
                return self._session
            except Exception as exc:
                debug('session exc:', exc, tb=True)
                with ignore_errors():
                    self._finish_session()
                if hidebadsessions:
                    debug('hiding bad session')
                    # TODO: Log the error?
                    return None
                self._stop_quietly()
                raise

        return pydevd, next_session

    def start_client(self, addr):
        """Return (pydevd "socket", start_session) with a new client socket."""
        addr = Address.from_raw(addr)
        with self.started():
            assert self.session is None
            client = create_client()
            connect(client, addr)
        pydevd = self._pydevd

        def start_session():
            self._check_ready_for_session()
            if self._server is not None:
                raise RuntimeError('running as server')
            if self._numsessions:
                raise RuntimeError('session stopped')

            try:
                self._bind_session(client)
                self._start_session('ptvsd.Client', None)
                return self._session
            except Exception:
                self._stop_quietly()
                raise

        return pydevd, start_session

    def start_session(self, session, threadname, timeout=None):
        """Start the debug session and remember it.

        If "session" is a client socket then a session is created
        from it.
        """
        self._check_ready_for_session()
        if self._server is not None:
            raise RuntimeError('running as server')

        self._bind_session(session)
        self._start_session(threadname, timeout)
        return self.session

    def close(self):
        """Stop all loops and release all resources."""
        if self._closed:
            raise DaemonClosedError('already closed')
        self._closed = True

        self._close()

    def re_build_breakpoints(self):
        """Restore the breakpoints to their last values."""
        if self.session is None:
            return
        return self.session.re_build_breakpoints()

    # internal methods

    def _check_ready_for_session(self):
        if self._closed:
            raise DaemonClosedError()
        if not self._started:
            raise DaemonStoppedError('never started')
        if self._pydevd is None:
            raise DaemonStoppedError()
        if self.session is not None:
            raise RuntimeError('session already started')

    def _close(self):
        self._stop()

        self._pydevd = None

        if self._wait_on_exit(self.exitcode):
            self._wait_for_user()

    def _start(self):
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

        with ignore_errors():
            self._finish_session()

        if sessionlock is not None:
            try:
                sessionlock.release()
            except Exception:
                pass

        if server is not None:
            with ignore_errors():
                close_socket(server)

        if self._pydevd is not None:
            with ignore_errors():
                close_socket(self._pydevd)

    def _stop_quietly(self):
        if self._closed:  # XXX wrong?
            return
        with ignore_errors():
            self._stop()

    def _handle_session_closing(self, session, kill=False):
        debug('handling closing session')
        if self._server is not None and not kill:
            self._finish_session(stop=False)
            return

        if not self._closed:  # XXX wrong?
            self._close()
        if kill and self._killonclose:
            if not self._exiting_via_atexit_handler:
                kill_current_proc()

    # internal session-related methods

    def _bind_session(self, session):
        session = DebugSession.from_raw(
            session,
            notify_closing=self._handle_session_closing,
            ownsock=True,
        )
        self._session = session
        self._numsessions += 1

    def _start_session(self, threadname, timeout):
        try:
            self.session.start(
                threadname,
                self._pydevd.pydevd_notify,
                self._pydevd.pydevd_request,
                timeout=timeout,
            )
        except Exception:
            with ignore_errors():
                self._finish_session()
            raise

    def _finish_session(self, stop=True):
        try:
            session = self._release_session(stop=stop)
            debug('session stopped')
        finally:
            sessionlock = self._sessionlock
            try:
                sessionlock.release()
            except Exception:  # TODO: Make it more specific?
                debug('session lock not released')
            else:
                debug('session lock released')

            if self._singlesession:
                debug('closing daemon after single session')
                self._wait_on_exit = session.get_wait_on_exit()
                try:
                    self.close()
                except DaemonClosedError:
                    pass

    def _release_session(self, stop=True):
        session = self.session
        if not self._singlesession:
            self._session = None

        if stop:
            exitcode = None
            if self._server is None:
                # Trigger a VSC "exited" event.
                exitcode = self.exitcode or 0
            session.stop(exitcode)
            session.close()

        return session

    # internal proc-related methods

    def _install_exit_handlers(self):
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

    def _handle_atexit(self):
        self._exiting_via_atexit_handler = True
        if not self._closed:  # XXX wrong?
            self._close()
        if self.session is not None:
            self.session.wait_until_stopped()

    def _handle_signal(self, signum, frame):
        if not self._closed:  # XXX wrong?
            self._close()
        if not self._exiting_via_atexit_handler:
            sys.exit(0)

    # internal methods for PyDevdSocket().

    def _handle_pydevd_message(self, cmdid, seq, text):
        if self.session is None or self.session.closed:
            # TODO: Do more than ignore?
            return
        self.session.handle_pydevd_message(cmdid, seq, text)

    def _handle_pydevd_close(self):
        if self._closed:  # XXX wrong?
            return
        self._close()

    def _getpeername(self):
        if self.session is None or self.session.closed:
            raise NotImplementedError
        return self.session.socket.getpeername()

    def _getsockname(self):
        if self.session is None or self.session.closed:
            raise NotImplementedError
        return self.session.socket.getsockname()
