from . import Closeable
from .debugadapter import DebugAdapter
from .debugsession import DebugSession


class DebugClient(Closeable):
    """A high-level abstraction of a debug client (i.e. editor)."""

    def __init__(self, port=8888):
        super(DebugClient, self).__init__()
        self._port = port
        self._adapter = None
        self._session = None

    # TODO: Support starting a remote debugger for testing
    # remote debugging?

    def start_debugger(self, argv):
        if self._adapter is not None:
            raise RuntimeError('debugger already running')
        self._adapter = DebugAdapter.start(argv, port=self._port)
        return self._adapter

    def launch_script(self, filename, *argv, **kwargs):
        if self._adapter is not None:
            raise RuntimeError('debugger already running')
        assert self._session is None

        argv = [
            filename,
        ] + list(argv)
        self._launch(argv, kwargs)
        return self._adapter, self._session

    def launch_module(self, module, *argv, **kwargs):
        if self._adapter is not None:
            raise RuntimeError('debugger already running')
        assert self._session is None

        argv = [
            '-m', module,
        ] + list(argv)
        self._launch(argv, kwargs)
        return self._adapter, self._session

    def attach(self, **kwargs):
        if self._adapter is None:
            raise RuntimeError('debugger not running')
        if self._session is not None:
            raise RuntimeError('already attached')

        self._attach(**kwargs)
        return self._session

    def detach(self):
        if self._session is None:
            raise RuntimeError('not attached')
        self._detach()

    # internal methods

    def _close(self):
        if self._adapter is not None:
            self._adapter.close()

    def _launch(self, argv, kwargs):
        self._adapter = DebugAdapter.start(
            argv,
            port=self._port,
        )
        self._attach(**kwargs)

    def _attach(self, **kwargs):
        addr = ('localhost', self._port)
        self._session = DebugSession.create(addr, **kwargs)

    def _detach(self):
        self._session.close()
        self._session = None
