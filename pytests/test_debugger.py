import sys
import pytest

from ptvsd.debugger import debug, LOCALHOST
from ptvsd.socket import Address


PROG = 'eggs'
PORT_ARGS = ['--port', '8888']
PYDEVD_DEFAULT_ARGS = ['--qt-support=auto']


def _get_args(*args, **kwargs):
    ptvsd_extras = kwargs.get('ptvsd_extras', [])
    prog = [kwargs.get('prog', PROG)]
    port = kwargs.get('port', PORT_ARGS)
    pydevd_args = kwargs.get('pydevd', PYDEVD_DEFAULT_ARGS)
    return prog + port + ptvsd_extras + pydevd_args + list(args)


class TestDebug(object):

    @pytest.fixture()
    def setUp(self):
        def _make_run(kind):
            def run(addr, name, *args, **kwargs):
                self._run(kind, addr, name, *args, **kwargs)
            return run
        self.runners = {}
        for kind in ('module', 'script', 'code', None):
            self.runners[kind] = _make_run(kind)
        self.kind = None
        self.args = None
        self.kwargs = None

    def _run(self, kind, *args, **kwargs):
        self.kind = kind
        self.args = args
        self.kwargs = kwargs

    def test_module(self, setUp):
        filename = 'spam'
        _, port = addr = (LOCALHOST, 8888)
        debug_id = 1
        debug_options = {'x': 'y'}
        debug(filename, port, debug_id, debug_options, 'module',
              _runners=self.runners, _extra=())

        assert self.kind == 'module'
        assert self.args == (addr, filename)
        assert self.kwargs == {'singlesession': True}

    def test_script(self, setUp):
        filename = 'spam.py'
        _, port = addr = (LOCALHOST, 8888)
        debug_id = 1
        debug_options = {'x': 'y'}
        debug(filename, port, debug_id, debug_options, 'script',
              _runners=self.runners, _extra=())

        assert self.kind == 'script'
        assert self.args == (addr, filename)
        assert self.kwargs == {'singlesession': True}

    def test_code(self, setUp):
        filename = "print('spam')"
        _, port = addr = (LOCALHOST, 8888)
        debug_id = 1
        debug_options = {'x': 'y'}
        debug(filename, port, debug_id, debug_options, 'code',
              _runners=self.runners, _extra=())

        assert self.kind == 'code'
        assert self.args == (addr, filename)
        assert self.kwargs == {'singlesession': True}

    def test_unsupported(self, setUp):
        filename = 'spam'
        _, port = addr = (LOCALHOST, 8888)
        debug_id = 1
        debug_options = {'x': 'y'}
        debug(filename, port, debug_id, debug_options, '???',
              _runners=self.runners, _extra=())

        assert self.kind is None
        assert self.args == (addr, filename)
        assert self.kwargs == {'singlesession': True}

    def test_extra_sys_argv(self, setUp):
        filename = 'spam.py'
        _, port = addr = (LOCALHOST, 8888)
        debug_id = 1
        debug_options = {'x': 'y'}
        extra = ['--eggs', 'abc']
        debug(filename, port, debug_id, debug_options, 'script',
              _runners=self.runners, _extra=extra)

        assert self.args == (addr, filename, '--eggs', 'abc')
        assert self.kwargs == {'singlesession': True}


class TestIntegration(object):

    @pytest.fixture(scope='function')
    def setUp(self):
        self.argv = None
        self.addr = None
        self.kwargs = None
        self._sys_argv = list(sys.argv)
        yield
        sys.argv[:] = self._sys_argv

    def _run(self, argv, addr, **kwargs):
        self.argv = argv
        self.addr = addr
        self.kwargs = kwargs

    def test_module(self, setUp):
        filename = 'spam'
        port = 8888
        debug_id = 1
        debug_options = {'x': 'y'}
        sys.argv = [filename]
        debug(filename, port, debug_id, debug_options, 'module',
              _run=self._run, _prog='eggs')

        assert self.argv == _get_args('--module', '--file', 'spam:', ptvsd_extras=['--client', LOCALHOST])
        assert self.addr == Address.as_client(None, port)
        assert self.kwargs == {'singlesession': True}

    def test_script(self, setUp):
        filename = 'spam.py'
        port = 8888
        debug_id = 1
        debug_options = {'x': 'y'}
        sys.argv = [filename]
        debug(filename, port, debug_id, debug_options, 'script',
              _run=self._run, _prog='eggs')

        assert self.argv == _get_args('--file', 'spam.py', ptvsd_extras=['--client', LOCALHOST])
        assert self.addr == Address.as_client(None, port)
        assert self.kwargs == {'singlesession': True}

    def test_code(self, setUp):
        filename = "print('spam')"
        port = 8888
        debug_id = 1
        debug_options = {'x': 'y'}
        sys.argv = [filename]
        debug(filename, port, debug_id, debug_options, 'code',
              _run=self._run, _prog='eggs')

        assert self.argv == _get_args('--file', filename, ptvsd_extras=['--client', LOCALHOST])
        assert self.addr == Address.as_client(None, port)
        assert self.kwargs == {'singlesession': True}

    def test_unsupported(self, setUp):
        filename = 'spam'
        port = 8888
        debug_id = 1
        debug_options = {'x': 'y'}
        sys.argv = [filename]
        debug(filename, port, debug_id, debug_options, '???',
              _run=self._run, _prog='eggs')

        assert self.argv == _get_args('--file', 'spam', ptvsd_extras=['--client', LOCALHOST])
        assert self.addr == Address.as_client(None, port)
        assert self.kwargs == {'singlesession': True}

    def test_extra_sys_argv(self, setUp):
        filename = 'spam.py'
        port = 8888
        debug_id = 1
        debug_options = {'x': 'y'}
        sys.argv = [filename, '--abc', 'xyz', '42']
        debug(filename, port, debug_id, debug_options, 'script',
              _run=self._run, _prog='eggs')

        assert self.argv == _get_args('--file', 'spam.py', '--abc', 'xyz', '42', ptvsd_extras=['--client', LOCALHOST])
        assert self.addr == Address.as_client(None, port)
        assert self.kwargs == {'singlesession': True}
