import os
import os.path
import sys

import _pydevd_bundle.pydevd_comm as pydevd_comm

from ptvsd import debugger
from tests.helpers import protocol
from ._binder import BinderBase


class Binder(BinderBase):

    def __init__(self, filename, module):
        super(Binder, self).__init__()
        self.filename = filename
        self.module = module

    def _run_debugger(self):
        def new_pydevd_sock(*args):
            self._start_ptvsd()
            return self.ptvsd.fakesock
        pydevd_comm.start_server = new_pydevd_sock
        pydevd_comm.start_client = new_pydevd_sock
        # Force a fresh pydevd.
        sys.modules.pop('pydevd', None)
        if self.module is None:
            debugger._run_file(self.address, self.filename)
        else:
            debugger._run_module(self.address, self.module)


class LivePyDevd(protocol.Daemon):

    @classmethod
    def parse_source(cls, source):
        kind, sep, name = source.partition(':')
        if kind == 'file':
            return name, None, False
        elif kind == 'module':
            parts = (name).split('.')
            filename = os.path.join(*parts) + '.py'
            return filename, name, False
        else:
            # TODO: Write source code to temp module?
            raise NotImplementedError

    def __init__(self, source):
        filename, module, owned = self.parse_source(source)
        self._filename = filename
        self._owned = owned
        self.binder = Binder(filename, module)

        super(LivePyDevd, self).__init__(self.binder.bind)

    def _close(self):
        super(LivePyDevd, self)._close()
        # TODO: Close pydevd somehow?

        if self._owned:
            os.unlink(self._filename)
