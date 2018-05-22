from ptvsd.socket import Address
from . import Closeable
from .proc import Proc


class DebugAdapter(Closeable):

    VERBOSE = False
    #VERBOSE = True

    PORT = 8888

    # generic factories

    @classmethod
    def start(cls, argv, **kwargs):
        def new_proc(argv, addr):
            if cls.VERBOSE:
                env = {
                    'PTVSD_DEBUG': '1',
                    'PTVSD_SOCKET_TIMEOUT': '1',
                }
            else:
                env = {}
            argv = list(argv)
            cls._ensure_addr(argv, addr)
            return Proc.start_python_module('ptvsd', argv, env=env)
        return cls._start(new_proc, argv, **kwargs)

    @classmethod
    def start_wrapper_script(cls, filename, argv, **kwargs):
        def new_proc(argv, addr):
            return Proc.start_python_script(filename, argv)
        return cls._start(new_proc, argv, **kwargs)

    # specific factory cases

    @classmethod
    def start_nodebug(cls, addr, name, kind='script'):
        if kind == 'script':
            argv = ['--nodebug', name]
        elif kind == 'module':
            argv = ['--nodebug', '-m', name]
        else:
            raise NotImplementedError
        return cls.start(argv, addr=addr)

    @classmethod
    def start_as_server(cls, addr, *args, **kwargs):
        addr = Address.as_server(*addr)
        return cls._start_as(addr, *args, server=False, **kwargs)

    @classmethod
    def start_as_client(cls, addr, *args, **kwargs):
        addr = Address.as_client(*addr)
        return cls._start_as(addr, *args, server=False, **kwargs)

    @classmethod
    def start_for_attach(cls, addr, *args, **kwargs):
        addr = Address.as_server(*addr)
        return cls._start_as(addr, *args, server=True, **kwargs)

    @classmethod
    def _start_as(cls, addr, name, kind='script', extra=None, server=False):
        argv = []
        if server:
            argv += ['--server']
        if kind == 'script':
            argv += [name]
        elif kind == 'module':
            argv += ['-m', name]
        else:
            raise NotImplementedError
        if extra:
            argv += list(extra)
        return cls.start(argv, addr=addr)

    @classmethod
    def start_embedded(cls, addr, filename, redirect_output=True):
        addr = Address.as_server(*addr)
        with open(filename, 'r+') as scriptfile:
            content = scriptfile.read()
            # TODO: Handle this case somehow?
            assert 'ptvsd.enable_attach' in content
        return cls.start_wrapper_script(filename, argv=[], addr=addr)

    @classmethod
    def _start(cls, new_proc, argv, addr=None):
        addr = Address.from_raw(addr, defaultport=cls.PORT)
        proc = new_proc(argv, addr)
        return cls(proc, addr, owned=True)

    @classmethod
    def _ensure_addr(cls, argv, addr):
        if '--host' in argv:
            raise ValueError("unexpected '--host' in argv")
        if '--server-host' in argv:
            raise ValueError("unexpected '--server-host' in argv")
        if '--port' in argv:
            raise ValueError("unexpected '--port' in argv")
        host, port = addr

        argv.insert(0, str(port))
        argv.insert(0, '--port')

        argv.insert(0, host)
        if addr.isserver:
            argv.insert(0, '--server-host')
        else:
            argv.insert(0, '--host')

    def __init__(self, proc, addr, owned=False):
        super(DebugAdapter, self).__init__()
        assert isinstance(proc, Proc)
        self._proc = proc
        self._addr = addr

    @property
    def address(self):
        return self._addr

    @property
    def pid(self):
        return self._proc.pid

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
