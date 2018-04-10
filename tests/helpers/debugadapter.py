from . import Closeable
from .debugsession import DebugSession
from .proc import Proc


class DebugAdapter(Closeable):

    VERBOSE = False
    #VERBOSE = True

    @classmethod
    def for_script(cls, filename, *argv, **kwargs):
        argv = [
            filename,
        ] + list(argv)
        return cls.start(argv, **kwargs)

    @classmethod
    def for_module(cls, module, *argv, **kwargs):
        argv = [
            '-m', module,
        ] + list(argv)
        return cls.start(argv, **kwargs)

    @classmethod
    def start(cls, argv, host='localhost', port=8888):
        addr = (host, port)
        argv = list(argv)
        if host and host not in ('localhost', '127.0.0.1'):
            argv.insert(0, host)
            argv.insert(0, '--host')
        if '--port' not in argv:
            argv.insert(0, str(port))
            argv.insert(0, '--port')
        proc = Proc.start_python_module('ptvsd', argv)
        return cls(proc, addr, owned=True)

    def __init__(self, proc, addr, owned=False):
        super(DebugAdapter, self).__init__()
        assert isinstance(proc, Proc)
        self._proc = proc
        self._addr = addr
        self._session = None

    @property
    def output(self):
        return self._proc.output

    @property
    def exitcode(self):
        return self._proc.exitcode

    def attach(self, **kwargs):
        if self._session is not None:
            raise RuntimeError('already attached')
        self._session = DebugSession.create(self._addr, **kwargs)
        return self._session

    def detach(self):
        if self._session is None:
            raise RuntimeError('not attached')
        session = self._session
        session.close()
        self._session = None
        return session.received

    def wait(self):
        self._proc.wait()

    # internal methods

    def _close(self):
        if self._session is not None:
            self._session.close()
        if self._proc is not None:
            self._proc.close()
        if self.VERBOSE:
            lines = self.output.decode('utf-8').splitlines()
            print(' + ' + '\n + '.join(lines))
