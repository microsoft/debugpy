import sys
import unittest

from ptvsd.debugger import debug, LOCALHOST
from ptvsd.socket import Address


class DebugTests(unittest.TestCase):

    def setUp(self):
        super(DebugTests, self).setUp()

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

    def test_module(self):
        filename = 'spam'
        _, port = addr = (LOCALHOST, 8888)
        debug_id = 1
        debug_options = {'x': 'y'}
        debug(filename, port, debug_id, debug_options, 'module',
              _runners=self.runners, _extra=())

        self.assertEqual(self.kind, 'module')
        self.assertEqual(self.args, (addr, filename))
        self.assertEqual(self.kwargs, {
            'singlesession': True,
        })

    def test_script(self):
        filename = 'spam.py'
        _, port = addr = (LOCALHOST, 8888)
        debug_id = 1
        debug_options = {'x': 'y'}
        debug(filename, port, debug_id, debug_options, 'script',
              _runners=self.runners, _extra=())

        self.assertEqual(self.kind, 'script')
        self.assertEqual(self.args, (addr, filename))
        self.assertEqual(self.kwargs, {
            'singlesession': True,
        })

    def test_code(self):
        filename = "print('spam')"
        _, port = addr = (LOCALHOST, 8888)
        debug_id = 1
        debug_options = {'x': 'y'}
        debug(filename, port, debug_id, debug_options, 'code',
              _runners=self.runners, _extra=())

        self.assertEqual(self.kind, 'code')
        self.assertEqual(self.args, (addr, filename))
        self.assertEqual(self.kwargs, {
            'singlesession': True,
        })

    def test_unsupported(self):
        filename = 'spam'
        _, port = addr = (LOCALHOST, 8888)
        debug_id = 1
        debug_options = {'x': 'y'}
        debug(filename, port, debug_id, debug_options, '???',
              _runners=self.runners, _extra=())

        self.assertIs(self.kind, None)
        self.assertEqual(self.args, (addr, filename))
        self.assertEqual(self.kwargs, {
            'singlesession': True,
        })

    def test_extra_sys_argv(self):
        filename = 'spam.py'
        _, port = addr = (LOCALHOST, 8888)
        debug_id = 1
        debug_options = {'x': 'y'}
        extra = ['--eggs', 'abc']
        debug(filename, port, debug_id, debug_options, 'script',
              _runners=self.runners, _extra=extra)

        self.assertEqual(self.args, (addr, filename, '--eggs', 'abc'))
        self.assertEqual(self.kwargs, {
            'singlesession': True,
        })


class IntegrationTests(unittest.TestCase):

    def setUp(self):
        super(IntegrationTests, self).setUp()
        self.argv = None
        self.addr = None
        self.kwargs = None
        self._sys_argv = list(sys.argv)

    def tearDown(self):
        sys.argv[:] = self._sys_argv
        super(IntegrationTests, self).tearDown()

    def _run(self, argv, addr, **kwargs):
        self.argv = argv
        self.addr = addr
        self.kwargs = kwargs

    def test_module(self):
        filename = 'spam'
        port = 8888
        debug_id = 1
        debug_options = {'x': 'y'}
        sys.argv = [filename]
        debug(filename, port, debug_id, debug_options, 'module',
              _run=self._run, _prog='eggs')

        self.assertEqual(self.argv, [
            'eggs',
            '--port', '8888',
            '--client', LOCALHOST,
            '--module',
            '--file', 'spam:',
        ])
        self.assertEqual(self.addr, Address.as_client(None, port))
        self.assertEqual(self.kwargs, {
            'singlesession': True,
        })

    def test_script(self):
        filename = 'spam.py'
        port = 8888
        debug_id = 1
        debug_options = {'x': 'y'}
        sys.argv = [filename]
        debug(filename, port, debug_id, debug_options, 'script',
              _run=self._run, _prog='eggs')

        self.assertEqual(self.argv, [
            'eggs',
            '--port', '8888',
            '--client', LOCALHOST,
            '--file', 'spam.py',
        ])
        self.assertEqual(self.addr, Address.as_client(None, port))
        self.assertEqual(self.kwargs, {
            'singlesession': True,
        })

    def test_code(self):
        filename = "print('spam')"
        port = 8888
        debug_id = 1
        debug_options = {'x': 'y'}
        sys.argv = [filename]
        debug(filename, port, debug_id, debug_options, 'code',
              _run=self._run, _prog='eggs')

        self.assertEqual(self.argv, [
            'eggs',
            '--port', '8888',
            '--client', LOCALHOST,
            '--file', filename,
        ])
        self.assertEqual(self.addr, Address.as_client(None, port))
        self.assertEqual(self.kwargs, {
            'singlesession': True,
        })

    def test_unsupported(self):
        filename = 'spam'
        port = 8888
        debug_id = 1
        debug_options = {'x': 'y'}
        sys.argv = [filename]
        debug(filename, port, debug_id, debug_options, '???',
              _run=self._run, _prog='eggs')

        self.assertEqual(self.argv, [
            'eggs',
            '--port', '8888',
            '--client', LOCALHOST,
            '--file', 'spam',
        ])
        self.assertEqual(self.addr, Address.as_client(None, port))
        self.assertEqual(self.kwargs, {
            'singlesession': True,
        })

    def test_extra_sys_argv(self):
        filename = 'spam.py'
        port = 8888
        debug_id = 1
        debug_options = {'x': 'y'}
        sys.argv = [filename, '--abc', 'xyz', '42']
        debug(filename, port, debug_id, debug_options, 'script',
              _run=self._run, _prog='eggs')

        self.assertEqual(self.argv, [
            'eggs',
            '--port', '8888',
            '--client', LOCALHOST,
            '--file', 'spam.py',
            '--abc', 'xyz',
            '42',
        ])
        self.assertEqual(self.addr, Address.as_client(None, port))
        self.assertEqual(self.kwargs, {
            'singlesession': True,
        })
