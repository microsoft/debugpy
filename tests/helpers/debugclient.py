from __future__ import absolute_import

import os
import traceback
import warnings

from ptvsd.socket import Address
from ptvsd._util import new_hidden_thread, Closeable, ClosedError
from .debugadapter import DebugAdapter, wait_for_socket_server
from .debugsession import DebugSession

# TODO: Add a helper function to start a remote debugger for testing
# remote debugging?


class _LifecycleClient(Closeable):

    SESSION = DebugSession

    def __init__(
            self,
            addr=None,
            port=8888,
            breakpoints=None,
            connecttimeout=1.0,
    ):
        super(_LifecycleClient, self).__init__()
        self._addr = Address.from_raw(addr, defaultport=port)
        self._connecttimeout = connecttimeout
        self._adapter = None
        self._session = None

        self._breakpoints = breakpoints

    @property
    def adapter(self):
        return self._adapter

    @property
    def session(self):
        return self._session

    def start_debugging(self, launchcfg):
        if self.closed:
            raise RuntimeError('debug client closed')
        if self._adapter is not None:
            raise RuntimeError('debugger already running')
        assert self._session is None

        raise NotImplementedError

    def stop_debugging(self):
        if self.closed:
            raise RuntimeError('debug client closed')
        if self._adapter is None:
            raise RuntimeError('debugger not running')

        if self._session is not None:
            self._detach()

        try:
            self._adapter.close()
        except ClosedError:
            pass
        self._adapter = None

    def attach_pid(self, pid, **kwargs):
        if self.closed:
            raise RuntimeError('debug client closed')
        if self._adapter is None:
            raise RuntimeError('debugger not running')
        if self._session is not None:
            raise RuntimeError('already attached')

        raise NotImplementedError

    def attach_socket(self, addr=None, adapter=None, **kwargs):
        if self.closed:
            raise RuntimeError('debug client closed')
        if adapter is None:
            adapter = self._adapter
        elif self._adapter is not None:
            raise RuntimeError('already using managed adapter')
        if adapter is None:
            raise RuntimeError('debugger not running')
        if self._session is not None:
            raise RuntimeError('already attached')

        if addr is None:
            addr = adapter.address
        self._attach(addr, **kwargs)
        return self._session

    def detach(self, adapter=None):
        if self.closed:
            raise RuntimeError('debug client closed')
        if self._session is None:
            raise RuntimeError('not attached')
        if adapter is None:
            adapter = self._adapter
        assert adapter is not None
        if not self._session.is_client:
            raise RuntimeError('detach not supported')

        self._detach()

    # internal methods

    def _close(self):
        if self._session is not None:
            try:
                self._session.close()
            except ClosedError:
                pass
        if self._adapter is not None:
            try:
                self._adapter.close()
            except ClosedError:
                pass

    def _launch(self,
                argv,
                script=None,
                wait_for_connect=None,
                detachable=True,
                env=None,
                cwd=None,
                **kwargs):
        if script is not None:
            def start(*args, **kwargs):
                return DebugAdapter.start_wrapper_script(
                    script, *args, **kwargs)
        else:
            start = DebugAdapter.start
        new_addr = Address.as_server if detachable else Address.as_client
        addr = new_addr(None, self._addr.port)
        self._adapter = start(argv, addr=addr, env=env, cwd=cwd)

        if wait_for_connect:
            wait_for_connect()
        else:
            wait_for_socket_server(addr)
            self._attach(addr, **kwargs)

    def _attach(self, addr, **kwargs):
        if addr is None:
            addr = self._addr
        assert addr.host == 'localhost'
        self._session = self.SESSION.create_client(addr, **kwargs)

    def _detach(self):
        session = self._session
        if session is None:
            return
        self._session = None
        try:
            session.close()
        except ClosedError:
            pass


class DebugClient(_LifecycleClient):
    """A high-level abstraction of a debug client (i.e. editor)."""

    # TODO: Manage breakpoints, etc.
    # TODO: Add debugger methods here (e.g. "pause").


class EasyDebugClient(DebugClient):
    def start_detached(self, argv):
        """Start an adapter in a background process."""
        if self.closed:
            raise RuntimeError('debug client closed')
        if self._adapter is not None:
            raise RuntimeError('debugger already running')
        assert self._session is None

        # TODO: Launch, handshake and detach?
        self._adapter = DebugAdapter.start(argv, port=self._port)
        return self._adapter

    def host_local_debugger(self,
                            argv,
                            script=None,
                            env=None,
                            cwd=None,
                            **kwargs):  # noqa
        if self.closed:
            raise RuntimeError('debug client closed')
        if self._adapter is not None:
            raise RuntimeError('debugger already running')
        assert self._session is None
        addr = ('localhost', self._addr.port)

        self._run_server_ex = None

        def run():
            try:
                self._session = self.SESSION.create_server(addr, **kwargs)
            except Exception as ex:
                self._run_server_ex = traceback.format_exc()

        t = new_hidden_thread(
            target=run,
            name='test.client',
        )
        t.start()

        def wait():
            t.join(timeout=self._connecttimeout)
            if t.is_alive():
                warnings.warn('timed out waiting for connection')
            if self._session is None:
                message = 'unable to connect after {} secs'.format(  # noqa
                    self._connecttimeout)
                if self._run_server_ex is None:
                    raise Exception(message)
                else:
                    message = message + os.linesep + self._run_server_ex # noqa
                    raise Exception(message)

            # The adapter will close when the connection does.

        self._launch(
            argv,
            script=script,
            wait_for_connect=wait,
            detachable=False,
            env=env,
            cwd=cwd)

        return self._adapter, self._session

    def launch_script(self, filename, *argv, **kwargs):
        if self.closed:
            raise RuntimeError('debug client closed')
        if self._adapter is not None:
            raise RuntimeError('debugger already running')
        assert self._session is None

        argv = [
            filename,
        ] + list(argv)
        if kwargs.pop('nodebug', False):
            argv.insert(0, '--nodebug')
        self._launch(argv, **kwargs)
        return self._adapter, self._session

    def launch_module(self, module, *argv, **kwargs):
        if self.closed:
            raise RuntimeError('debug client closed')
        if self._adapter is not None:
            raise RuntimeError('debugger already running')
        assert self._session is None

        argv = [
            '-m',
            module,
        ] + list(argv)
        if kwargs.pop('nodebug', False):
            argv.insert(0, '--nodebug')
        self._launch(argv, **kwargs)
        return self._adapter, self._session
