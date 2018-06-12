import contextlib
import sys
import threading

from ptvsd import wrapper
from ptvsd.socket import (
    close_socket, create_server, create_client, connect, Address)
from .exit_handlers import (
    ExitHandlers, UnsupportedSignalError,
    kill_current_proc)
from .session import PyDevdDebugSession
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

class DaemonBase(object):
    """The base class for DAP daemons."""

    SESSION = None

    exitcode = 0

    def __init__(self, wait_for_user=_wait_for_user,
                 addhandlers=True, killonclose=True,
                 singlesession=False):

        self._started = False
        self._closed = False

        # socket-related

        self._sock = None  # set when started
        self._server = None

        # session-related

        self._singlesession = singlesession

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
        if self._closed:
            return False
        if self._sock is None:
            return False
        return True

    def start(self):
        """Return the "socket" to use for pydevd after setting it up."""
        if self._closed:
            raise DaemonClosedError()
        if self._started:
            raise RuntimeError('already started')
        self._started = True

        sock = self._start()
        self._sock = sock
        return sock

    def start_server(self, addr, hidebadsessions=True):
        """Return ("socket", next_session) with a new server socket."""
        addr = Address.from_raw(addr)
        with self.started():
            assert self._sessionlock is None
            assert self.session is None
            self._server = create_server(addr.host, addr.port)
            self._sessionlock = threading.Lock()
        sock = self._sock

        def check_ready(**kwargs):
            self._check_ready_for_session(**kwargs)
            if self._server is None:
                raise DaemonStoppedError()

        def next_session(timeout=None, **kwargs):
            server = self._server
            sessionlock = self._sessionlock
            check_ready(checksession=False)

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
                self._start_session_safely('ptvsd.Server', timeout=timeout)
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

        return sock, next_session

    def start_client(self, addr):
        """Return ("socket", start_session) with a new client socket."""
        addr = Address.from_raw(addr)
        with self.started():
            assert self.session is None
            client = create_client()
            connect(client, addr)
        sock = self._sock

        def start_session(**kwargs):
            self._check_ready_for_session()
            if self._server is not None:
                raise RuntimeError('running as server')
            if self._numsessions:
                raise RuntimeError('session stopped')

            try:
                self._bind_session(client)
                self._start_session_safely('ptvsd.Client', **kwargs)
                return self._session
            except Exception:
                self._stop_quietly()
                raise

        return sock, start_session

    def start_session(self, session, threadname, **kwargs):
        """Start the debug session and remember it.

        If "session" is a client socket then a session is created
        from it.
        """
        self._check_ready_for_session()
        if self._server is not None:
            raise RuntimeError('running as server')

        self._bind_session(session)
        self._start_session_safely(threadname, **kwargs)
        return self.session

    def close(self):
        """Stop all loops and release all resources."""
        if self._closed:
            raise DaemonClosedError('already closed')
        self._closed = True

        self._close()

    # internal methods

    def _check_ready_for_session(self, checksession=True):
        if self._closed:
            raise DaemonClosedError()
        if not self._started:
            raise DaemonStoppedError('never started')
        if self._sock is None:
            raise DaemonStoppedError()
        if checksession and self.session is not None:
            raise RuntimeError('session already started')

    def _close(self):
        self._stop()

        self._sock = None

        if self._wait_on_exit(self.exitcode):
            self._wait_for_user()

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

        if self._sock is not None:
            with ignore_errors():
                close_socket(self._sock)

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
        session = self.SESSION.from_raw(
            session,
            notify_closing=self._handle_session_closing,
            ownsock=True,
        )
        self._session = session
        self._numsessions += 1

    def _start_session_safely(self, threadname, **kwargs):
        try:
            self._start_session(threadname, **kwargs)
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

    # methods for subclasses to override

    def _start(self):
        """Return the debugger client socket after starting the daemon."""
        raise NotImplementedError

    def _start_session(self, threadname, **kwargs):
        self.session.start(
            threadname,
            **kwargs
        )


class Daemon(DaemonBase):
    """The process-level manager for the VSC protocol debug adapter."""

    SESSION = PyDevdDebugSession

    @property
    def pydevd(self):
        return self._sock

    def re_build_breakpoints(self):
        """Restore the breakpoints to their last values."""
        if self.session is None:
            return
        return self.session.re_build_breakpoints()

    # internal methods

    def _start(self):
        return wrapper.PydevdSocket(
            self._handle_pydevd_message,
            self._handle_pydevd_close,
            self._getpeername,
            self._getsockname,
        )

    def _start_session(self, threadname, **kwargs):
        super(Daemon, self)._start_session(
            threadname,
            pydevd_notify=self.pydevd.pydevd_notify,
            pydevd_request=self.pydevd.pydevd_request,
            **kwargs
        )

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
