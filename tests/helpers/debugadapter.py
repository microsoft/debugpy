import os
import os.path
import socket
import time

from ptvsd.socket import Address
from . import Closeable
from .proc import Proc
from .. import PROJECT_ROOT


COPIED_ENV = [
    'PYTHONHASHSEED',

    # Windows
    #'ALLUSERSPROFILE',
    #'APPDATA',
    #'CLIENTNAME',
    #'COMMONPROGRAMFILES',
    #'COMMONPROGRAMFILES(X86)',
    #'COMMONPROGRAMW6432',
    #'COMPUTERNAME',
    #'COMSPEC',
    #'DRIVERDATA',
    #'HOMEDRIVE',
    #'HOMEPATH',
    #'LOCALAPPDATA',
    #'LOGONSERVER',
    #'NUMBER_OF_PROCESSORS',
    #'OS',
    #'PATH',
    #'PATHEXT',
    #'PROCESSOR_ARCHITECTURE',
    #'PROCESSOR_IDENTIFIER',
    #'PROCESSOR_LEVEL',
    #'PROCESSOR_REVISION',
    #'PROGRAMDATA',
    #'PROGRAMFILES',
    #'PROGRAMFILES(X86)',
    #'PROGRAMW6432',
    #'PSMODULEPATH',
    #'PUBLIC',
    #'SESSIONNAME',
    'SYSTEMDRIVE',
    'SYSTEMROOT',
    #'TEMP',
    #'TMP',
    #'USERDOMAIN',
    #'USERDOMAIN_ROAMINGPROFILE',
    #'USERNAME',
    #'USERPROFILE',
    'WINDIR',
]


def _copy_env(verbose=False, env=None):
    variables = {k: v for k, v in os.environ.items() if k in COPIED_ENV}
    # TODO: Be smarter about the seed?
    variables.setdefault('PYTHONHASHSEED', '1234')
    if verbose:
        variables.update({
            'PTVSD_DEBUG': '1',
            'PTVSD_SOCKET_TIMEOUT': '1',
        })
    if env is not None:
        variables.update(env)

    # Ensure Project root is always in current path.
    python_path = variables.get('PYTHONPATH', None)
    if python_path is None:
        variables['PYTHONPATH'] = PROJECT_ROOT
    else:
        variables['PYTHONPATH'] = os.pathsep.join([PROJECT_ROOT, python_path])

    return variables


def wait_for_socket_server(addr, timeout=3.0, **kwargs):
    start_time = time.time()
    while True:
        try:
            sock = socket.create_connection((addr.host, addr.port))
            sock.close()
            return
        except Exception:
            pass
        time.sleep(0.1)
        if time.time() - start_time > timeout:
            raise ConnectionRefusedError('Timeout waiting for connection')


class DebugAdapter(Closeable):

    VERBOSE = False
    #VERBOSE = True

    PORT = 8888

    # generic factories

    @classmethod
    def start(cls, argv, env=None, cwd=None, **kwargs):
        def new_proc(argv, addr, **kwds):
            env_vars = _copy_env(verbose=cls.VERBOSE, env=env)
            argv = list(argv)
            cls._ensure_addr(argv, addr)
            return Proc.start_python_module(
                'ptvsd',
                argv,
                env=env_vars,
                cwd=cwd,
                **kwds
            )
        return cls._start(new_proc, argv, **kwargs)

    @classmethod
    def start_wrapper_script(cls, filename, argv, env=None, cwd=None, **kwargs): # noqa
        def new_proc(argv, addr, **kwds):
            env_vars = _copy_env(verbose=cls.VERBOSE, env=env)
            return Proc.start_python_script(
                filename,
                argv,
                env=env_vars,
                cwd=cwd,
                **kwds
            )
        return cls._start(new_proc, argv, **kwargs)

    @classmethod
    def start_wrapper_module(cls, modulename, argv, env=None, cwd=None, **kwargs): # noqa
        def new_proc(argv, addr, **kwds):
            env_vars = _copy_env(verbose=cls.VERBOSE, env=env)
            return Proc.start_python_module(
                modulename,
                argv,
                env=env_vars,
                cwd=cwd,
                **kwds
            )
        return cls._start(new_proc, argv, **kwargs)

    # specific factory cases

    @classmethod
    def start_nodebug(cls, addr, name, kind='script', **kwargs):
        if kind == 'script':
            argv = ['--nodebug', name]
        elif kind == 'module':
            argv = ['--nodebug', '-m', name]
        else:
            raise NotImplementedError
        return cls.start(argv, addr=addr, **kwargs)

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
        adapter = cls._start_as(addr, *args, server=True, **kwargs)
        wait_for_socket_server(addr)
        return adapter

    @classmethod
    def _start_as(cls, addr, name, kind='script', extra=None, server=False,
                  **kwargs):
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
        return cls.start(argv, addr=addr, **kwargs)

    @classmethod
    def start_embedded(cls, addr, filename, argv=[], **kwargs):
        addr = Address.as_server(*addr)
        with open(filename, 'r+') as scriptfile:
            content = scriptfile.read()
            # TODO: Handle this case somehow?
            assert 'ptvsd.enable_attach' in content
        adapter = cls.start_wrapper_script(
            filename,
            argv=argv,
            addr=addr,
            **kwargs
        )
        wait_for_socket_server(addr, **kwargs)
        return adapter

    @classmethod
    def _start(cls, new_proc, argv, addr=None, **kwargs):
        addr = Address.from_raw(addr, defaultport=cls.PORT)
        proc = new_proc(argv, addr, **kwargs)
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

    def wait(self, *argv):
        self._proc.wait(*argv)

    # internal methods

    def _close(self):
        if self._proc is not None:
            self._proc.close()
        if self.VERBOSE:
            lines = self.output.decode('utf-8').splitlines()
            print(' + ' + '\n + '.join(lines))
