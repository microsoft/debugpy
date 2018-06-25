from __future__ import absolute_import

try:
    import queue
except ImportError:
    import Queue as queue  # Python 2.7
import subprocess
import sys

from ptvsd._util import new_hidden_thread
from . import Closeable


_NOT_SET = object()


def process_lines(stream, notify_received, notify_done=None, check_done=None,
                  close=True):
    # (inspired by https://stackoverflow.com/questions/375427)
    if check_done is None:
        check_done = (lambda: False)
    line = stream.readline()
    while line and not check_done():  # Break on EOF.
        notify_received(line)
        try:
            line = stream.readline()
        except ValueError:  # stream closed
            line = ''
    if notify_done is not None:
        notify_done()
    if close:
        # TODO: What if stream doesn't have close()?
        stream.close()


def collect_lines(stream, buf=None, notify_received=None, **kwargs):
    # (inspired by https://stackoverflow.com/questions/375427)
    if buf is None:
        buf = queue.Queue()

    if notify_received is None:
        notify_received = buf.put
    else:
        def notify_received(line, _notify=notify_received):
            _notify(line)
            buf.put(line)

    t = new_hidden_thread(
        target=process_lines,
        args=(stream, notify_received),
        kwargs=kwargs,
        name='test.proc.output',
    )
    t.start()

    return buf, t


class ProcOutput(object):
    """A tracker for a process's std* output."""

    # TODO: Support stderr?
    # TODO: Support buffer max size?
    # TODO: Support cache max size?

    def __init__(self, proc):
        if proc.stdout is None:
            raise ValueError('proc.stdout is None')

        self._proc = proc
        self._output = b''

        def notify_received(line):
            self._output += line
        self._buffer, _ = collect_lines(
            proc.stdout,
            notify_received=notify_received,
        )

    def __str__(self):
        self._flush()
        return self._output.decode('utf-8')

    def __bytes__(self):
        self._flush()
        return self._output

    def __iter__(self):
        return self

    def __next__(self):
        while True:
            try:
                return self._buffer.get(timeout=0.01)
            except queue.Empty:
                if self._proc.poll() is not None:
                    raise StopIteration

    next = __next__  # for Python 2.7

    def readline(self):
        try:
            self._buffer.get_nowait()
        except queue.Empty:
            return b''

    def decode(self, *args, **kwargs):
        self._flush()
        return self._output.decode(*args, **kwargs)

    def reset(self):
        # TODO: There's a small race here.
        self._flush()
        self._output = b''

    # internal methods

    def _flush(self):
        for _ in range(self._buffer.qsize()):
            try:
                self._buffer.get_nowait()
            except queue.Empty:
                break


class Proc(Closeable):
    """A wrapper around a subprocess.Popen object."""

    VERBOSE = False
    #VERBOSE = True

    ARGV = [
        sys.executable,
        '-u',  # stdout/stderr unbuffered
        ]

    @classmethod
    def start_python_script(cls, filename, argv, **kwargs):
        argv = list(cls.ARGV) + [
            filename,
        ] + argv
        return cls.start(argv, **kwargs)

    @classmethod
    def start_python_module(cls, module, argv, **kwargs):
        argv = list(cls.ARGV) + [
            '-m', module,
        ] + argv
        return cls.start(argv, **kwargs)

    @classmethod
    def start(cls, argv, env=None, stdout=_NOT_SET, stderr=_NOT_SET):
        if env is None:
            env = {}
        if cls.VERBOSE:
            env.setdefault('PTVSD_DEBUG', '1')
        proc = cls._start(argv, env, stdout, stderr)
        return cls(proc, owned=True)

    @classmethod
    def _start(cls, argv, env, stdout, stderr):
        if stdout is _NOT_SET:
            stdout = subprocess.PIPE
        if stderr is _NOT_SET:
            stderr = subprocess.STDOUT
        proc = subprocess.Popen(
            argv,
            stdout=stdout,
            stderr=stderr,
            #close_fds=('posix' in sys.builtin_module_names),
            env=env,
        )
        return proc

    def __init__(self, proc, owned=False):
        super(Proc, self).__init__()
        assert isinstance(proc, subprocess.Popen)
        self._proc = proc
        if proc.stdout is sys.stdout or proc.stdout is None:
            self._output = None
        else:
            self._output = ProcOutput(proc)

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
        return self._output

    @property
    def exitcode(self):
        # TODO: Use proc.poll()?
        return self._proc.returncode

    def wait(self):
        # TODO: Use proc.communicate()?
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
