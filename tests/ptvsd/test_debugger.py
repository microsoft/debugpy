import unittest

from ptvsd.debugger import debug


class DebugTests(unittest.TestCase):

    def setUp(self):
        super(DebugTests, self).setUp()
        self.runners = {}
        for kind in ('module', 'script', 'code', None):
            def run(addr, name, kind=kind, **kwargs):
                self._run(kind, addr, name, **kwargs)
            self.runners[kind] = run
        self.kind = None
        self.args = None
        self.kwargs = None

    def _run(self, kind, *args, **kwargs):
        self.kind = kind
        self.args = args
        self.kwargs = kwargs

    def test_module(self):
        filename = 'spam'
        _, port = addr = (None, 8888)
        debug_id = 1
        debug_options = {'x': 'y'}
        debug(filename, port, debug_id, debug_options, 'module',
              _runners=self.runners)

        self.assertEqual(self.kind, 'module')
        self.assertEqual(self.args, (addr, filename))
        self.assertEqual(self.kwargs, {})

    def test_script(self):
        filename = 'spam.py'
        _, port = addr = (None, 8888)
        debug_id = 1
        debug_options = {'x': 'y'}
        debug(filename, port, debug_id, debug_options, 'script',
              _runners=self.runners)

        self.assertEqual(self.kind, 'script')
        self.assertEqual(self.args, (addr, filename))
        self.assertEqual(self.kwargs, {})

    def test_code(self):
        filename = "print('spam')"
        _, port = addr = (None, 8888)
        debug_id = 1
        debug_options = {'x': 'y'}
        debug(filename, port, debug_id, debug_options, 'code',
              _runners=self.runners)

        self.assertEqual(self.kind, 'code')
        self.assertEqual(self.args, (addr, filename))
        self.assertEqual(self.kwargs, {})

    def test_unsupported(self):
        filename = 'spam'
        _, port = addr = (None, 8888)
        debug_id = 1
        debug_options = {'x': 'y'}
        debug(filename, port, debug_id, debug_options, '???',
              _runners=self.runners)

        self.assertIs(self.kind, None)
        self.assertEqual(self.args, (addr, filename))
        self.assertEqual(self.kwargs, {})


class IntegrationTests(unittest.TestCase):

    def setUp(self):
        super(IntegrationTests, self).setUp()
        self.argv = None
        self.kwargs = None

    def _run(self, argv, **kwargs):
        self.argv = argv
        self.kwargs = kwargs

    def test_module(self):
        filename = 'spam'
        port = 8888
        debug_id = 1
        debug_options = {'x': 'y'}
        debug(filename, port, debug_id, debug_options, 'module',
              _run=self._run, _prog='eggs')

        self.assertEqual(self.argv, [
            'eggs',
            '--port', '8888',
            '--module',
            '--file', 'spam:',
        ])
        self.assertEqual(self.kwargs, {})

    def test_script(self):
        filename = 'spam.py'
        port = 8888
        debug_id = 1
        debug_options = {'x': 'y'}
        debug(filename, port, debug_id, debug_options, 'script',
              _run=self._run, _prog='eggs')

        self.assertEqual(self.argv, [
            'eggs',
            '--port', '8888',
            '--file', 'spam.py',
        ])
        self.assertEqual(self.kwargs, {})

    def test_code(self):
        filename = "print('spam')"
        port = 8888
        debug_id = 1
        debug_options = {'x': 'y'}
        debug(filename, port, debug_id, debug_options, 'code',
              _run=self._run, _prog='eggs')

        self.assertEqual(self.argv, [
            'eggs',
            '--port', '8888',
            '--file', filename,
        ])
        self.assertEqual(self.kwargs, {})

    def test_unsupported(self):
        filename = 'spam'
        port = 8888
        debug_id = 1
        debug_options = {'x': 'y'}
        debug(filename, port, debug_id, debug_options, '???',
              _run=self._run, _prog='eggs')

        self.assertEqual(self.argv, [
            'eggs',
            '--port', '8888',
            '--file', 'spam',
        ])
        self.assertEqual(self.kwargs, {})
