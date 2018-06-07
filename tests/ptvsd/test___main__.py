import unittest

from ptvsd.socket import Address
from ptvsd.__main__ import parse_args
from tests.helpers._io import captured_stdio


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
            'address': Address.as_server(None, 8888),
            'nodebug': False,
            'single_session': False,
        })
        self.assertEqual(extra, [])

    def test_module_server(self):
        args, extra = parse_args([
            'eggs',
            '--server-host', '10.0.1.1',
            '--port', '8888',
            '-m', 'spam',
        ])

        self.assertEqual(vars(args), {
            'kind': 'module',
            'name': 'spam',
            'address': Address.as_server('10.0.1.1', 8888),
            'nodebug': False,
            'single_session': False,
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
            'address': Address.as_client(None, 8888),
            'nodebug': True,
            'single_session': False,
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
            'address': Address.as_server(None, 8888),
            'nodebug': False,
            'single_session': False,
        })
        self.assertEqual(extra, [])

    def test_script_server(self):
        args, extra = parse_args([
            'eggs',
            '--server-host', '10.0.1.1',
            '--port', '8888',
            'spam.py',
        ])

        self.assertEqual(vars(args), {
            'kind': 'script',
            'name': 'spam.py',
            'address': Address.as_server('10.0.1.1', 8888),
            'nodebug': False,
            'single_session': False,
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
            'address': Address.as_client(None, 8888),
            'nodebug': True,
            'single_session': False,
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
            'address': Address.as_client('1.2.3.4', 8888),
            'nodebug': False,
            'single_session': False,
        })
        self.assertEqual(extra, [])

    def test_remote_localhost(self):
        args, extra = parse_args([
            'eggs',
            '--host', 'localhost',
            '--port', '8888',
            'spam.py',
        ])

        self.assertEqual(vars(args), {
            'kind': 'script',
            'name': 'spam.py',
            'address': Address.as_client('localhost', 8888),
            'nodebug': False,
            'single_session': False,
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
            'address': Address.as_client('1.2.3.4', 8888),
            'nodebug': True,
            'single_session': False,
        })
        self.assertEqual(extra, [])

    def test_remote_single_session(self):
        args, extra = parse_args([
            'eggs',
            '--single-session',
            '--port', '8888',
            'spam.py',
        ])

        self.assertEqual(vars(args), {
            'kind': 'script',
            'name': 'spam.py',
            'address': Address.as_server('localhost', 8888),
            'nodebug': False,
            'single_session': True,
        })
        self.assertEqual(extra, [])

    def test_local_single_session(self):
        args, extra = parse_args([
            'eggs',
            '--single-session',
            '--server-host', '1.2.3.4',
            '--port', '8888',
            'spam.py',
        ])

        self.assertEqual(vars(args), {
            'kind': 'script',
            'name': 'spam.py',
            'address': Address.as_server('1.2.3.4', 8888),
            'nodebug': False,
            'single_session': True,
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
            'address': Address.as_server(None, 8888),
            'nodebug': False,
            'single_session': False,
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
            'address': Address.as_client(None, 8888),
            'nodebug': True,
            'single_session': False,
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

    def test_empty_host(self):
        args, extra = parse_args([
            'eggs',
            '--host', '',
            '--port', '8888',
            'spam.py',
        ])

        self.assertEqual(vars(args), {
            'kind': 'script',
            'name': 'spam.py',
            'address': Address.as_server('', 8888),
            'nodebug': False,
            'single_session': False,
        })
        self.assertEqual(extra, [])

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
            'address': Address.as_client('1.2.3.4', 8888),
            'nodebug': False,
            'single_session': False,
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
            'address': Address.as_client('1.2.3.4', 8888),
            'nodebug': True,
            'single_session': False,
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
            'address': Address.as_server(None, 8888),
            'nodebug': False,
            'single_session': False,
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
            'address': Address.as_client(None, 8888),
            'nodebug': True,
            'single_session': False,
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
            'address': Address.as_server(None, 8888),
            'nodebug': False,
            'single_session': False,
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
            'address': Address.as_client(None, 8888),
            'nodebug': True,
            'single_session': False,
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
            'address': Address.as_server(None, 8888),
            'nodebug': False,
            'single_session': False,
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
            'address': Address.as_client(None, 8888),
            'nodebug': True,
            'single_session': False,
        })
        self.assertEqual(extra, ['--module'])
