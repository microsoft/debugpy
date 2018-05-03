import subprocess
import sys

from . import Closeable


class Proc(Closeable):
    """A wrapper around a subprocess.Popen object."""

    VERBOSE = False
    #VERBOSE = True

    @classmethod
    def start_python_script(cls, filename, argv):
        argv = [
            sys.executable,
            filename,
        ] + argv
        return cls.start(argv)

    @classmethod
    def start_python_module(cls, module, argv):
        argv = [
            sys.executable,
            '-m', module,
        ] + argv
        return cls.start(argv)

    @classmethod
    def start(cls, argv):
        proc = cls._start(argv)
        return cls(proc, owned=True)

    @classmethod
    def _start(cls, argv):
        proc = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        return proc

    def __init__(self, proc, owned=False):
        super(Proc, self).__init__()
        assert isinstance(proc, subprocess.Popen)
        self._proc = proc

    # TODO: Emulate class-only methods?
    #def __getattribute__(self, name):
    #    val = super(Proc, self).__getattribute__(name)
    #    if isinstance(type(self).__dict__.get(name), classmethod):
    #        raise AttributeError(name)
    #    return val

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
        if self.VERBOSE:
            lines = self.output.decode('utf-8').splitlines()
            print(' + ' + '\n + '.join(lines))
