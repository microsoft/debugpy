import subprocess
import sys

from . import Closeable


class Proc(Closeable):
    """A wrapper around a subprocess.Popen object."""

    VERBOSE = False
    #VERBOSE = True

    @classmethod
    def start_python_script(cls, filename, argv, **kwargs):
        argv = [
            sys.executable,
            filename,
        ] + argv
        return cls.start(argv, **kwargs)

    @classmethod
    def start_python_module(cls, module, argv, **kwargs):
        argv = [
            sys.executable,
            '-m', module,
        ] + argv
        return cls.start(argv, **kwargs)

    @classmethod
    def start(cls, argv, env=None, stdout=None, stderr=None):
        if env is None:
            env = {}
        if cls.VERBOSE:
            env.setdefault('PTVSD_DEBUG', '1')
        proc = cls._start(argv, env, stdout, stderr)
        return cls(proc, owned=True)

    @classmethod
    def _start(cls, argv, env, stdout, stderr):
        if stdout is None:
            stdout = subprocess.PIPE
        if stderr is None:
            stderr = subprocess.STDOUT
        proc = subprocess.Popen(
            argv,
            stdout=stdout,
            stderr=stderr,
            env=env,
        )
        return proc

    def __init__(self, proc, owned=False):
        super(Proc, self).__init__()
        assert isinstance(proc, subprocess.Popen)
        self._proc = proc
        if proc.stdout is sys.stdout or proc.stdout is None:
            self._output = None

    # TODO: Emulate class-only methods?
    #def __getattribute__(self, name):
    #    val = super(Proc, self).__getattribute__(name)
    #    if isinstance(type(self).__dict__.get(name), classmethod):
    #        raise AttributeError(name)
    #    return val

    @property
    def pid(self):
        return self._proc.pid

    @property
    def output(self):
        try:
            # TODO: Could there be more?
            return self._output
        except AttributeError:
            # TODO: Wait until proc done?  (piped output blocks)
            self._output = self._proc.stdout.read()
            return self._output

    @property
    def exitcode(self):
        return self._proc.returncode

    def wait(self):
        self._proc.wait()

    # internal methods

    def _close(self):
        if self._proc is not None:
            try:
                self._proc.kill()
            except OSError:
                # Already killed.
                pass
            else:
                if self.VERBOSE:
                    print('proc killed')
        if self.VERBOSE:
            out = self.output
            if out is not None:
                lines = out.decode('utf-8').splitlines()
                print(' + ' + '\n + '.join(lines))
