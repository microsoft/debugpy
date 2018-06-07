import os
import os.path
import threading
import warnings

import ptvsd._local
from tests.helpers import protocol
from tests.helpers.threading import acquire_with_timeout
from ._binder import BinderBase


class Binder(BinderBase):

    def __init__(self, filename, module, **kwargs):
        super(Binder, self).__init__(**kwargs)
        self.filename = filename
        self.module = module
        self._lock = threading.Lock()
        self._lock.acquire()
        self._closeondone = True

    def _run_debugger(self):
        def new_pydevd_sock(*args):
            self._start_ptvsd()
            return self.ptvsd.fakesock
        if self.module is None:
            run = ptvsd._local.run_file
            name = self.filename
        else:
            run = ptvsd._local.run_module
            name = self.module
        run(
            self.address,
            name,
            start_server=new_pydevd_sock,
            start_client=new_pydevd_sock,
            wait_for_user=(lambda: None),
            addhandlers=False,
            killonclose=False,
        )

        # Block until "done" debugging.
        if not acquire_with_timeout(self._lock, timeout=3):
            # This shouldn't happen since the timeout on event waiting
            # is this long.
            warnings.warn('timeout out waiting for "done"')
        return self._closeondone

    def done(self, close=True):
        self._closeondone = close
        self._lock.release()


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

    def __init__(self, source, **kwargs):
        filename, module, owned = self.parse_source(source)
        self._filename = filename
        self._owned = owned
        self.binder = Binder(filename, module, **kwargs)

        super(LivePyDevd, self).__init__(self.binder.bind)

    @property
    def thread(self):
        return self.binder.thread

    def _close(self):
        # Note that we do not call self.binder.done() here, though it
        # might make sense as a fallback.  Instead, we do so directly
        # in the relevant test cases.
        super(LivePyDevd, self)._close()
        # TODO: Close pydevd somehow?

        if self._owned:
            os.unlink(self._filename)
        if self.binder.ptvsd is not None:
            self.binder.ptvsd.close()
