import contextlib
from io import StringIO, BytesIO
import sys
import unittest

from ptvsd.socket import Address
from ptvsd.__main__ import parse_args


if sys.version_info < (3,):
    Buffer = BytesIO
else:
    Buffer = StringIO


@contextlib.contextmanager
def captured_stdio(out=None, err=None):
    if out is None:
        if err is None:
            out = err = Buffer()
        elif err is False:
            out = Buffer()
    elif err is None and out is False:
        err = Buffer()
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
        })
        self.assertEqual(extra, ['--module'])
