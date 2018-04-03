import sys
import unittest

from _pydevd_bundle import pydevd_comm

import ptvsd.wrapper
from ptvsd.__main__ import run_module, run_file


class FakePyDevd(object):

    def __init__(self, __file__, handle_main):
        self.__file__ = __file__
        self.handle_main = handle_main

    def main(self):
        self.handle_main()


class RunBase(object):

    def setUp(self):
        super(RunBase, self).setUp()
        self.argv = None
        self.kwargs = None

    def _run(self, argv, **kwargs):
        self.argv = argv
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
        self.assertEqual(self.kwargs, {})

    def test_executable(self):
        addr = (None, 8888)
        run_file(addr, 'spam.py', _run=self._run)

        self.assertEqual(self.argv, [
            sys.argv[0],
            '--port', '8888',
            '--file', 'spam.py',
        ])
        self.assertEqual(self.kwargs, {})


class IntegratedRunTests(unittest.TestCase):

    def setUp(self):
        super(IntegratedRunTests, self).setUp()
        self.__main__ = sys.modules['__main__']
        self.argv = sys.argv
        ptvsd.wrapper.ptvsd_sys_exit_code = 0
        self.start_server = pydevd_comm.start_server
        self.start_client = pydevd_comm.start_client

        self.pydevd = None
        self.kwargs = None
        self.maincalls = 0
        self.mainexc = None

    def tearDown(self):
        sys.argv[:] = self.argv
        sys.modules['__main__'] = self.__main__
        sys.modules.pop('__main___orig', None)
        ptvsd.wrapper.ptvsd_sys_exit_code = 0
        pydevd_comm.start_server = self.start_server
        pydevd_comm.start_client = self.start_client
        # We shouldn't need to restore __main__.start_*.
        super(IntegratedRunTests, self).tearDown()

    def _install(self, pydevd, **kwargs):
        self.pydevd = pydevd
        self.kwargs = kwargs

    def _main(self):
        self.maincalls += 1
        if self.mainexc is not None:
            raise self.mainexc

    def test_run(self):
        pydevd = FakePyDevd('pydevd/pydevd.py', self._main)
        addr = (None, 8888)
        run_file(addr, 'spam.py', _pydevd=pydevd, _install=self._install)

        self.assertEqual(self.pydevd, pydevd)
        self.assertEqual(self.kwargs, {})
        self.assertEqual(self.maincalls, 1)
        self.assertEqual(sys.argv, [
            sys.argv[0],
            '--port', '8888',
            '--file', 'spam.py',
        ])
        self.assertEqual(ptvsd.wrapper.ptvsd_sys_exit_code, 0)

    def test_failure(self):
        self.mainexc = RuntimeError('boom!')
        pydevd = FakePyDevd('pydevd/pydevd.py', self._main)
        addr = (None, 8888)
        with self.assertRaises(RuntimeError) as cm:
            run_file(addr, 'spam.py', _pydevd=pydevd, _install=self._install)
        exc = cm.exception

        self.assertEqual(self.pydevd, pydevd)
        self.assertEqual(self.kwargs, {})
        self.assertEqual(self.maincalls, 1)
        self.assertEqual(sys.argv, [
            sys.argv[0],
            '--port', '8888',
            '--file', 'spam.py',
        ])
        self.assertEqual(ptvsd.wrapper.ptvsd_sys_exit_code, 0)
        self.assertIs(exc, self.mainexc)

    def test_exit(self):
        self.mainexc = SystemExit(1)
        pydevd = FakePyDevd('pydevd/pydevd.py', self._main)
        addr = (None, 8888)
        with self.assertRaises(SystemExit):
            run_file(addr, 'spam.py', _pydevd=pydevd, _install=self._install)

        self.assertEqual(self.pydevd, pydevd)
        self.assertEqual(self.kwargs, {})
        self.assertEqual(self.maincalls, 1)
        self.assertEqual(sys.argv, [
            sys.argv[0],
            '--port', '8888',
            '--file', 'spam.py',
        ])
        self.assertEqual(ptvsd.wrapper.ptvsd_sys_exit_code, 1)

    def test_installed(self):
        pydevd = FakePyDevd('pydevd/pydevd.py', self._main)
        addr = (None, 8888)
        run_file(addr, 'spam.py', _pydevd=pydevd)

        self.assertIs(pydevd_comm.start_server, ptvsd.wrapper.start_server)
        self.assertIs(pydevd_comm.start_client, ptvsd.wrapper.start_client)
        self.assertIs(pydevd.start_server, ptvsd.wrapper.start_server)
        self.assertIs(pydevd.start_client, ptvsd.wrapper.start_client)
        __main__ = sys.modules['__main__']
        self.assertIs(__main__.start_server, ptvsd.wrapper.start_server)
        self.assertIs(__main__.start_client, ptvsd.wrapper.start_client)
