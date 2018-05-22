import contextlib
import sys
import unittest

from ptvsd.socket import Address


class AddressTests(unittest.TestCase):

    if sys.version_info < (3,):
        @contextlib.contextmanager
        def subTest(self, *args, **kwargs):
            yield

    def test_from_raw(self):
        serverlocal = Address.as_server('localhost', 9876)
        serverremote = Address.as_server('1.2.3.4', 9876)
        clientlocal = Address.as_client('localhost', 9876)
        clientremote = Address.as_client('1.2.3.4', 9876)
        default = Address(None, 1111)
        external = Address('', 1111)
        values = [
            (serverlocal, serverlocal),
            (serverremote, serverremote),
            (clientlocal, clientlocal),
            (clientremote, clientremote),
            (None, default),
            ('', external),
            ([], default),
            ({}, default),
            (9876, serverlocal),
            ('localhost:9876', clientlocal),
            ('1.2.3.4:9876', clientremote),
            ('*:9876', Address.as_server('', 9876)),
            ('*', external),
            (':9876', Address.as_server('', 9876)),
            ('localhost', Address('localhost', 1111)),
            (':', external),
            (dict(host='localhost'), Address('localhost', 1111)),
            (dict(port=9876), serverlocal),
            (dict(host=None, port=9876), serverlocal),
            (dict(host='localhost', port=9876), clientlocal),
            (dict(host='localhost', port='9876'), clientlocal),
        ]
        for value, expected in values:
            with self.subTest(value):
                addr = Address.from_raw(value, defaultport=1111)

                self.assertEqual(addr, expected)

    def test_as_server_valid_address(self):
        for host in ['localhost', '127.0.0.1', '::', '1.2.3.4']:
            with self.subTest(host):
                addr = Address.as_server(host, 9786)

                self.assertEqual(
                    addr,
                    Address(host, 9786, isserver=True),
                )

    def test_as_server_public_host(self):
        addr = Address.as_server('', 9786)

        self.assertEqual(
            addr,
            Address('', 9786, isserver=True),
        )

    def test_as_server_default_host(self):
        addr = Address.as_server(None, 9786)

        self.assertEqual(
            addr,
            Address('localhost', 9786, isserver=True),
        )

    def test_as_server_bad_port(self):
        port = None
        for host in [None, '', 'localhost', '1.2.3.4']:
            with self.subTest((host, port)):
                with self.assertRaises(TypeError):
                    Address.as_server(host, port)

        for port in ['', -1, 0, 65536]:
            for host in [None, '', 'localhost', '1.2.3.4']:
                with self.subTest((host, port)):
                    with self.assertRaises(ValueError):
                        Address.as_server(host, port)

    def test_as_client_valid_address(self):
        for host in ['localhost', '127.0.0.1', '::', '1.2.3.4']:
            with self.subTest(host):
                addr = Address.as_client(host, 9786)

                self.assertEqual(
                    addr,
                    Address(host, 9786, isserver=False),
                )

    def test_as_client_public_host(self):
        addr = Address.as_client('', 9786)

        self.assertEqual(
            addr,
            Address('', 9786, isserver=False),
        )

    def test_as_client_default_host(self):
        addr = Address.as_client(None, 9786)

        self.assertEqual(
            addr,
            Address('localhost', 9786, isserver=False),
        )

    def test_as_client_bad_port(self):
        port = None
        for host in [None, '', 'localhost', '1.2.3.4']:
            with self.subTest((host, port)):
                with self.assertRaises(TypeError):
                    Address.as_client(host, port)

        for port in ['', -1, 0, 65536]:
            for host in [None, '', 'localhost', '1.2.3.4']:
                with self.subTest((host, port)):
                    with self.assertRaises(ValueError):
                        Address.as_client(host, port)

    def test_new_valid_address(self):
        for host in ['localhost', '127.0.0.1', '::', '1.2.3.4']:
            with self.subTest(host):
                addr = Address(host, 9786)

                self.assertEqual(
                    addr,
                    Address(host, 9786, isserver=False),
                )

    def test_new_public_host(self):
        addr = Address('', 9786)

        self.assertEqual(
            addr,
            Address('', 9786, isserver=True),
        )

    def test_new_default_host(self):
        addr = Address(None, 9786)

        self.assertEqual(
            addr,
            Address('localhost', 9786, isserver=True),
        )

    def test_new_wildcard_host(self):
        addr = Address('*', 9786)

        self.assertEqual(
            addr,
            Address('', 9786, isserver=True),
        )

    def test_new_bad_port(self):
        port = None
        for host in [None, '', 'localhost', '1.2.3.4']:
            with self.subTest((host, port)):
                with self.assertRaises(TypeError):
                    Address(host, port)

        for port in ['', -1, 0, 65536]:
            for host in [None, '', 'localhost', '1.2.3.4']:
                with self.subTest((host, port)):
                    with self.assertRaises(ValueError):
                        Address(host, port)
