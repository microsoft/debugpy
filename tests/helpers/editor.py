from . import Closeable
from .debugadapter import DebugAdapter


class FakeEditor(Closeable):

    def __init__(self, port=8888):
        super(FakeEditor, self).__init__()
        self._port = port
        self._adapter = None

    def start_debugger(self, argv):
        if self._adapter is not None:
            raise RuntimeError('debugger already running')
        self._adapter = DebugAdapter.start(argv, port=self._port)
        return self._adapter

    def launch_script(self, filename, *argv, **kwargs):
        if self._adapter is not None:
            raise RuntimeError('debugger already running')
        self._adapter = DebugAdapter.for_script(filename, *argv,
                                                port=self._port)
        return self._adapter, self._adapter.attach(**kwargs)

    def launch_module(self, module, *argv, **kwargs):
        if self._adapter is not None:
            raise RuntimeError('debugger already running')
        self._adapter = DebugAdapter.for_module(module, *argv,
                                                port=self._port)
        return self._adapter, self._adapter.attach(**kwargs)

    def detach(self):
        if self._adapter is None:
            raise RuntimeError('debugger not running')
        self._adapter.detach()

    def attach(self, **kwargs):
        if self._adapter is None:
            raise RuntimeError('debugger not running')
        self._adapter, self._adapter.attach(**kwargs)

    # internal methods

    def _close(self):
        if self._adapter is not None:
            self._adapter.close()
