from . import Closeable
from .proc import Proc


class DebugAdapter(Closeable):

    VERBOSE = False
    #VERBOSE = True

    PORT = 8888

    @classmethod
    def start(cls, argv, **kwargs):
        def new_proc(argv, host, port):
            argv = list(argv)
            cls._ensure_addr(argv, host, port)
            return Proc.start_python_module('ptvsd', argv)
        return cls._start(new_proc, argv, **kwargs)

    @classmethod
    def start_wrapper_script(cls, filename, argv, **kwargs):
        def new_proc(argv, host, port):
            return Proc.start_python_script(filename, argv)
        return cls._start(new_proc, argv, **kwargs)

    @classmethod
    def _start(cls, new_proc, argv, host='localhost', port=None):
        if port is None:
            port = cls.PORT
        addr = (host, port)
        proc = new_proc(argv, host, port)
        return cls(proc, addr, owned=True)

    @classmethod
    def _ensure_addr(cls, argv, host, port):
        if '--host' in argv:
            raise ValueError("unexpected '--host' in argv")
        if '--port' in argv:
            raise ValueError("unexpected '--port' in argv")

        argv.insert(0, str(port))
        argv.insert(0, '--port')

        if host and host not in ('localhost', '127.0.0.1'):
            argv.insert(0, host)
            argv.insert(0, '--host')

    def __init__(self, proc, addr, owned=False):
        super(DebugAdapter, self).__init__()
        assert isinstance(proc, Proc)
        self._proc = proc
        self._addr = addr

    @property
    def output(self):
        # TODO: Decode here?
        return self._proc.output

    @property
    def exitcode(self):
        return self._proc.exitcode

    def wait(self):
        self._proc.wait()

    # internal methods

    def _close(self):
        if self._proc is not None:
            self._proc.close()
        if self.VERBOSE:
            lines = self.output.decode('utf-8').splitlines()
            print(' + ' + '\n + '.join(lines))
