import sys
import unittest

from _pydevd_bundle import pydevd_comm

import ptvsd.pydevd_hooks
from ptvsd.socket import Address
from ptvsd._main import run_module, run_file


class FakePyDevd(object):

    def __init__(self, __file__, handle_main):
        self.__file__ = __file__
        self.handle_main = handle_main

    @property
    def __name__(self):
        return object.__repr__(self)

    def main(self):
        self.handle_main()


class RunBase(object):

    def setUp(self):
        super(RunBase, self).setUp()
        self.argv = None
        self.addr = None
        self.kwargs = None

    def _run(self, argv, addr, **kwargs):
        self.argv = argv
        self.addr = addr
        self.kwargs = kwargs


class RunModuleTests(RunBase, unittest.TestCase):

    def test_local(self):
        addr = (None, 8888)
        run_module(addr, 'spam', _run=self._run, _prog='eggs')

        self.assertEqual(self.argv, [
            'eggs',
            '--port', '8888',
            '--module',
            '--file', 'spam:',
        ])
        self.assertEqual(self.addr, Address.as_server(*addr))
        self.assertEqual(self.kwargs, {})

    def test_server(self):
        addr = Address.as_server('10.0.1.1', 8888)
        run_module(addr, 'spam', _run=self._run, _prog='eggs')

        self.assertEqual(self.argv, [
            'eggs',
            '--port', '8888',
            '--module',
            '--file', 'spam:',
        ])
        self.assertEqual(self.addr, Address.as_server(*addr))
        self.assertEqual(self.kwargs, {})

    def test_remote(self):
        addr = ('1.2.3.4', 8888)
        run_module(addr, 'spam', _run=self._run, _prog='eggs')

        self.assertEqual(self.argv, [
            'eggs',
            '--port', '8888',
            '--client', '1.2.3.4',
            '--module',
            '--file', 'spam:',
        ])
        self.assertEqual(self.addr, Address.as_client(*addr))
        self.assertEqual(self.kwargs, {})

    def test_remote_localhost(self):
        addr = Address.as_client(None, 8888)
        run_module(addr, 'spam', _run=self._run, _prog='eggs')

        self.assertEqual(self.argv, [
            'eggs',
            '--port', '8888',
            '--client', 'localhost',
            '--module',
            '--file', 'spam:',
        ])
        self.assertEqual(self.addr, Address.as_client(*addr))
        self.assertEqual(self.kwargs, {})

    def test_extra(self):
        addr = (None, 8888)
        run_module(addr, 'spam', '--vm_type', 'xyz', '--', '--DEBUG',
                   _run=self._run, _prog='eggs')

        self.assertEqual(self.argv, [
            'eggs',
            '--port', '8888',
            '--vm_type', 'xyz',
            '--module',
            '--file', 'spam:',
            '--DEBUG',
        ])
        self.assertEqual(self.addr, Address.as_server(*addr))
        self.assertEqual(self.kwargs, {})

    def test_executable(self):
        addr = (None, 8888)
        run_module(addr, 'spam', _run=self._run)

        self.assertEqual(self.argv, [
            sys.argv[0],
            '--port', '8888',
            '--module',
            '--file', 'spam:',
        ])
        self.assertEqual(self.addr, Address.as_server(*addr))
        self.assertEqual(self.kwargs, {})


class RunScriptTests(RunBase, unittest.TestCase):

    def test_local(self):
        addr = (None, 8888)
        run_file(addr, 'spam.py', _run=self._run, _prog='eggs')

        self.assertEqual(self.argv, [
            'eggs',
            '--port', '8888',
            '--file', 'spam.py',
        ])
        self.assertEqual(self.addr, Address.as_server(*addr))
        self.assertEqual(self.kwargs, {})

    def test_server(self):
        addr = Address.as_server('10.0.1.1', 8888)
        run_file(addr, 'spam.py', _run=self._run, _prog='eggs')

        self.assertEqual(self.argv, [
            'eggs',
            '--port', '8888',
            '--file', 'spam.py',
        ])
        self.assertEqual(self.addr, Address.as_server(*addr))
        self.assertEqual(self.kwargs, {})

    def test_remote(self):
        addr = ('1.2.3.4', 8888)
        run_file(addr, 'spam.py', _run=self._run, _prog='eggs')

        self.assertEqual(self.argv, [
            'eggs',
            '--port', '8888',
            '--client', '1.2.3.4',
            '--file', 'spam.py',
        ])
        self.assertEqual(self.addr, Address.as_client(*addr))
        self.assertEqual(self.kwargs, {})

    def test_remote_localhost(self):
        addr = Address.as_client(None, 8888)
        run_file(addr, 'spam.py', _run=self._run, _prog='eggs')

        self.assertEqual(self.argv, [
            'eggs',
            '--port', '8888',
            '--client', 'localhost',
            '--file', 'spam.py',
        ])
        self.assertEqual(self.addr, Address.as_client(*addr))
        self.assertEqual(self.kwargs, {})

    def test_extra(self):
        addr = (None, 8888)
        run_file(addr, 'spam.py', '--vm_type', 'xyz', '--', '--DEBUG',
                 _run=self._run, _prog='eggs')

        self.assertEqual(self.argv, [
            'eggs',
            '--port', '8888',
            '--vm_type', 'xyz',
            '--file', 'spam.py',
            '--DEBUG',
        ])
        self.assertEqual(self.addr, Address.as_server(*addr))
        self.assertEqual(self.kwargs, {})

    def test_executable(self):
        addr = (None, 8888)
        run_file(addr, 'spam.py', _run=self._run)

        self.assertEqual(self.argv, [
            sys.argv[0],
            '--port', '8888',
            '--file', 'spam.py',
        ])
        self.assertEqual(self.addr, Address.as_server(*addr))
        self.assertEqual(self.kwargs, {})


class IntegratedRunTests(unittest.TestCase):

    def setUp(self):
        super(IntegratedRunTests, self).setUp()
        self.___main__ = sys.modules['__main__']
        self._argv = sys.argv
        self._start_server = pydevd_comm.start_server
        self._start_client = pydevd_comm.start_client

        self.pydevd = None
        self.addr = None
        self.kwargs = None
        self.maincalls = 0
        self.mainexc = None
        self.exitcode = -1

    def tearDown(self):
        sys.argv[:] = self._argv
        sys.modules['__main__'] = self.___main__
        sys.modules.pop('__main___orig', None)
        pydevd_comm.start_server = self._start_server
        pydevd_comm.start_client = self._start_client
        # We shouldn't need to restore __main__.start_*.
        super(IntegratedRunTests, self).tearDown()

    def _install(self, pydevd, addr, **kwargs):
        self.pydevd = pydevd
        self.addr = addr
        self.kwargs = kwargs
        return self

    def _main(self):
        self.maincalls += 1
        if self.mainexc is not None:
            raise self.mainexc

    def test_run(self):
        pydevd = FakePyDevd('pydevd/pydevd.py', self._main)
        addr = (None, 8888)
        run_file(addr, 'spam.py', _pydevd=pydevd, _install=self._install)

        self.assertEqual(self.pydevd, pydevd)
        self.assertEqual(self.addr, Address.as_server(*addr))
        self.assertEqual(self.kwargs, {})
        self.assertEqual(self.maincalls, 1)
        self.assertEqual(sys.argv, [
            sys.argv[0],
            '--port', '8888',
            '--file', 'spam.py',
        ])
        self.assertEqual(self.exitcode, -1)

    def test_failure(self):
        self.mainexc = RuntimeError('boom!')
        pydevd = FakePyDevd('pydevd/pydevd.py', self._main)
        addr = (None, 8888)
        with self.assertRaises(RuntimeError) as cm:
            run_file(addr, 'spam.py', _pydevd=pydevd, _install=self._install)
        exc = cm.exception

        self.assertEqual(self.pydevd, pydevd)
        self.assertEqual(self.addr, Address.as_server(*addr))
        self.assertEqual(self.kwargs, {})
        self.assertEqual(self.maincalls, 1)
        self.assertEqual(sys.argv, [
            sys.argv[0],
            '--port', '8888',
            '--file', 'spam.py',
        ])
        self.assertEqual(self.exitcode, -1)  # TODO: Is this right?
        self.assertIs(exc, self.mainexc)

    def test_exit(self):
        self.mainexc = SystemExit(1)
        pydevd = FakePyDevd('pydevd/pydevd.py', self._main)
        addr = (None, 8888)
        with self.assertRaises(SystemExit):
            run_file(addr, 'spam.py', _pydevd=pydevd, _install=self._install)

        self.assertEqual(self.pydevd, pydevd)
        self.assertEqual(self.addr, Address.as_server(*addr))
        self.assertEqual(self.kwargs, {})
        self.assertEqual(self.maincalls, 1)
        self.assertEqual(sys.argv, [
            sys.argv[0],
            '--port', '8888',
            '--file', 'spam.py',
        ])
        self.assertEqual(self.exitcode, 1)

    def test_installed(self):
        pydevd = FakePyDevd('pydevd/pydevd.py', self._main)
        addr = (None, 8888)
        run_file(addr, 'spam.py', _pydevd=pydevd)

        __main__ = sys.modules['__main__']
        expected_server = ptvsd.pydevd_hooks.start_server
        expected_client = ptvsd.pydevd_hooks.start_client
        for mod in (pydevd_comm, pydevd, __main__):
            start_server = getattr(mod, 'start_server')
            if hasattr(start_server, 'orig'):
                start_server = start_server.orig
            start_client = getattr(mod, 'start_client')
            if hasattr(start_client, 'orig'):
                start_client = start_client.orig

            self.assertIs(start_server, expected_server,
                          '(module {})'.format(mod.__name__))
            self.assertIs(start_client, expected_client,
                          '(module {})'.format(mod.__name__))
