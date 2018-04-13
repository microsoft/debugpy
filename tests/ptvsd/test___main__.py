import contextlib
from io import StringIO
import sys
import unittest

from _pydevd_bundle import pydevd_comm

import ptvsd.pydevd_hooks
from ptvsd.__main__ import run_module, run_file, parse_args

if sys.version_info < (3,):
    from io import BytesIO as StringIO  # noqa


@contextlib.contextmanager
def captured_stdio(out=None, err=None):
    if out is None:
        if err is None:
            out = err = StringIO()
        elif err is False:
            out = StringIO()
    elif err is None and out is False:
        err = StringIO()
    if out is False:
        out = None
    if err is False:
        err = None

    orig = sys.stdout, sys.stderr
    if out is not None:
        sys.stdout = out
    if err is not None:
        sys.stderr = err
    try:
        yield out, err
    finally:
        sys.stdout, sys.stderr = orig


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
        self.___main__ = sys.modules['__main__']
        self._argv = sys.argv
        self._start_server = pydevd_comm.start_server
        self._start_client = pydevd_comm.start_client

        self.pydevd = None
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

    def _install(self, pydevd, **kwargs):
        self.pydevd = pydevd
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


class ParseArgsTests(unittest.TestCase):

    def test_module(self):
        args, extra = parse_args([
            'eggs',
            '--port', '8888',
            '-m', 'spam',
        ])

        self.assertEqual(vars(args), {
            'kind': 'module',
            'name': 'spam',
            'address': (None, 8888),
            'nodebug': False,
        })
        self.assertEqual(extra, [])

    def test_module_nodebug(self):
        args, extra = parse_args([
            'eggs',
            '--nodebug',
            '--port', '8888',
            '-m', 'spam',
        ])

        self.assertEqual(vars(args), {
            'kind': 'module',
            'name': 'spam',
            'address': (None, 8888),
            'nodebug': True,
        })
        self.assertEqual(extra, [])

    def test_script(self):
        args, extra = parse_args([
            'eggs',
            '--port', '8888',
            'spam.py',
        ])

        self.assertEqual(vars(args), {
            'kind': 'script',
            'name': 'spam.py',
            'address': (None, 8888),
            'nodebug': False,
        })
        self.assertEqual(extra, [])

    def test_script_nodebug(self):
        args, extra = parse_args([
            'eggs',
            '--nodebug',
            '--port', '8888',
            'spam.py',
        ])

        self.assertEqual(vars(args), {
            'kind': 'script',
            'name': 'spam.py',
            'address': (None, 8888),
            'nodebug': True,
        })
        self.assertEqual(extra, [])

    def test_remote(self):
        args, extra = parse_args([
            'eggs',
            '--host', '1.2.3.4',
            '--port', '8888',
            'spam.py',
        ])

        self.assertEqual(vars(args), {
            'kind': 'script',
            'name': 'spam.py',
            'address': ('1.2.3.4', 8888),
            'nodebug': False,
        })
        self.assertEqual(extra, [])

    def test_remote_nodebug(self):
        args, extra = parse_args([
            'eggs',
            '--nodebug',
            '--host', '1.2.3.4',
            '--port', '8888',
            'spam.py',
        ])

        self.assertEqual(vars(args), {
            'kind': 'script',
            'name': 'spam.py',
            'address': ('1.2.3.4', 8888),
            'nodebug': True,
        })
        self.assertEqual(extra, [])

    def test_extra(self):
        args, extra = parse_args([
            'eggs',
            '--DEBUG',
            '--port', '8888',
            '--vm_type', '???',
            'spam.py',
            '--xyz', '123',
            'abc',
            '--cmd-line',
            '--',
            'foo',
            '--server',
            '--bar'
        ])

        self.assertEqual(vars(args), {
            'kind': 'script',
            'name': 'spam.py',
            'address': (None, 8888),
            'nodebug': False,
        })
        self.assertEqual(extra, [
            '--DEBUG',
            '--vm_type', '???',
            '--xyz', '123',
            'abc',
            '--cmd-line',
            'foo',
            '--server',
            '--bar',
        ])

    def test_extra_nodebug(self):
        args, extra = parse_args([
            'eggs',
            '--DEBUG',
            '--nodebug',
            '--port', '8888',
            '--vm_type', '???',
            'spam.py',
            '--xyz', '123',
            'abc',
            '--cmd-line',
            '--',
            'foo',
            '--server',
            '--bar'
        ])

        self.assertEqual(vars(args), {
            'kind': 'script',
            'name': 'spam.py',
            'address': (None, 8888),
            'nodebug': True,
        })
        self.assertEqual(extra, [
            '--DEBUG',
            '--vm_type', '???',
            '--xyz', '123',
            'abc',
            '--cmd-line',
            'foo',
            '--server',
            '--bar',
        ])

    def test_unsupported_arg(self):
        with self.assertRaises(SystemExit):
            with captured_stdio():
                parse_args([
                    'eggs',
                    '--port', '8888',
                    '--xyz', '123',
                    'spam.py',
                ])

    def test_backward_compatibility_host(self):
        args, extra = parse_args([
            'eggs',
            '--client', '1.2.3.4',
            '--port', '8888',
            '-m', 'spam',
        ])

        self.assertEqual(vars(args), {
            'kind': 'module',
            'name': 'spam',
            'address': ('1.2.3.4', 8888),
            'nodebug': False,
        })
        self.assertEqual(extra, [])

    def test_backward_compatibility_host_nodebug(self):
        args, extra = parse_args([
            'eggs',
            '--nodebug',
            '--client', '1.2.3.4',
            '--port', '8888',
            '-m', 'spam',
        ])

        self.assertEqual(vars(args), {
            'kind': 'module',
            'name': 'spam',
            'address': ('1.2.3.4', 8888),
            'nodebug': True,
        })
        self.assertEqual(extra, [])

    def test_backward_compatibility_module(self):
        args, extra = parse_args([
            'eggs',
            '--port', '8888',
            '--module',
            '--file', 'spam:',
        ])

        self.assertEqual(vars(args), {
            'kind': 'module',
            'name': 'spam',
            'address': (None, 8888),
            'nodebug': False,
        })
        self.assertEqual(extra, [])

    def test_backward_compatibility_module_nodebug(self):
        args, extra = parse_args([
            'eggs',
            '--nodebug',
            '--port', '8888',
            '--module',
            '--file', 'spam:',
        ])

        self.assertEqual(vars(args), {
            'kind': 'module',
            'name': 'spam',
            'address': (None, 8888),
            'nodebug': True,
        })
        self.assertEqual(extra, [])

    def test_backward_compatibility_script(self):
        args, extra = parse_args([
            'eggs',
            '--port', '8888',
            '--file', 'spam.py',
        ])

        self.assertEqual(vars(args), {
            'kind': 'script',
            'name': 'spam.py',
            'address': (None, 8888),
            'nodebug': False,
        })
        self.assertEqual(extra, [])

    def test_backward_compatibility_script_nodebug(self):
        args, extra = parse_args([
            'eggs',
            '--nodebug',
            '--port', '8888',
            '--file', 'spam.py',
        ])

        self.assertEqual(vars(args), {
            'kind': 'script',
            'name': 'spam.py',
            'address': (None, 8888),
            'nodebug': True,
        })
        self.assertEqual(extra, [])

    def test_pseudo_backward_compatibility(self):
        args, extra = parse_args([
            'eggs',
            '--port', '8888',
            '--module',
            '--file', 'spam',
        ])

        self.assertEqual(vars(args), {
            'kind': 'script',
            'name': 'spam',
            'address': (None, 8888),
            'nodebug': False,
        })
        self.assertEqual(extra, ['--module'])

    def test_pseudo_backward_compatibility_nodebug(self):
        args, extra = parse_args([
            'eggs',
            '--nodebug',
            '--port', '8888',
            '--module',
            '--file', 'spam',
        ])

        self.assertEqual(vars(args), {
            'kind': 'script',
            'name': 'spam',
            'address': (None, 8888),
            'nodebug': True,
        })
        self.assertEqual(extra, ['--module'])
