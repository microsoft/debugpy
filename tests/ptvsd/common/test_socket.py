# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import platform
import pytest
from ptvsd.common.socket import Address
from ptvsd.common.socket import create_server, close_socket


class TestSocketServerReuse(object):
    HOST1 = "127.0.0.1"
    # NOTE: Windows allows loopback range 127/8. Some flavors of Linux support
    # 127/8 range. Mac by default supports only 127/0. Configuring /etc/network/interface
    # for this one test is overkill so use '0.0.0.0' on Mac instead.
    HOST2 = "127.0.0.2" if platform.system() in ["Windows", "Linux"] else "0.0.0.0"

    def test_reuse_same_address_port(self):
        # NOTE: This test should ensure that same address port can be used by two
        # sockets. This to prevent accidental changes to socket options. In Windows
        # SO_REUSEADDR flag allows two sockets to bind to same address:port combination.
        # Windows should always use SO_EXCLUSIVEADDRUSE
        sock1 = create_server(self.HOST1, 0)
        try:
            _, PORT1 = sock1.getsockname()
            with pytest.raises(Exception):
                create_server(self.HOST1, PORT1)
        finally:
            close_socket(sock1)

    def test_reuse_same_port(self):
        try:
            sock1, sock2 = None, None
            sock1 = create_server(self.HOST1, 0)
            _, PORT1 = sock1.getsockname()
            sock2 = create_server(self.HOST2, PORT1)
            assert sock1.getsockname() == (self.HOST1, PORT1)
            assert sock2.getsockname() == (self.HOST2, PORT1)
        except Exception:
            pytest.fail()
        finally:
            if sock1 is not None:
                close_socket(sock1)
            if sock2 is not None:
                close_socket(sock2)


class TestAddress(object):
    def test_from_raw(self):
        serverlocal = Address.as_server("localhost", 9876)
        serverremote = Address.as_server("1.2.3.4", 9876)
        clientlocal = Address.as_client("localhost", 9876)
        clientremote = Address.as_client("1.2.3.4", 9876)
        default = Address(None, 1111)
        external = Address("", 1111)
        values = [
            (serverlocal, serverlocal),
            (serverremote, serverremote),
            (clientlocal, clientlocal),
            (clientremote, clientremote),
            (None, default),
            ("", external),
            ([], default),
            ({}, default),
            (9876, serverlocal),
            ("localhost:9876", clientlocal),
            ("1.2.3.4:9876", clientremote),
            ("*:9876", Address.as_server("", 9876)),
            ("*", external),
            (":9876", Address.as_server("", 9876)),
            ("localhost", Address("localhost", 1111)),
            (":", external),
            (dict(host="localhost"), Address("localhost", 1111)),
            (dict(port=9876), serverlocal),
            (dict(host=None, port=9876), serverlocal),
            (dict(host="localhost", port=9876), clientlocal),
            (dict(host="localhost", port="9876"), clientlocal),
        ]
        for value, expected in values:
            addr = Address.from_raw(value, defaultport=1111)
            assert addr == expected

    @pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "::", "1.2.3.4"])
    def test_as_server_valid_address(self, host):
        addr = Address.as_server(host, 9786)
        assert addr == Address(host, 9786, isserver=True)

    def test_as_server_public_host(self):
        addr = Address.as_server("", 9786)
        assert addr == Address("", 9786, isserver=True)

    def test_as_server_default_host(self):
        addr = Address.as_server(None, 9786)
        assert addr == Address("localhost", 9786, isserver=True)

    @pytest.mark.parametrize("host", [None, "", "localhost", "1.2.3.4"])
    def test_as_server_bad_port(self, host):
        port = None
        with pytest.raises(TypeError):
            Address.as_server(host, port)

    @pytest.mark.parametrize("host", [None, "", "localhost", "1.2.3.4"])
    @pytest.mark.parametrize("port", ["", -1, 65536])
    def test_as_server_bad_port2(self, host, port):
        with pytest.raises(ValueError):
            Address.as_server(host, port)

    @pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "::", "1.2.3.4"])
    def test_as_client_valid_address(self, host):
        addr = Address.as_client(host, 9786)
        assert addr == Address(host, 9786, isserver=False)

    def test_as_client_public_host(self):
        addr = Address.as_client("", 9786)
        assert addr == Address("", 9786, isserver=False)

    def test_as_client_default_host(self):
        addr = Address.as_client(None, 9786)
        assert addr == Address("localhost", 9786, isserver=False)

    @pytest.mark.parametrize("host", [None, "", "localhost", "1.2.3.4"])
    def test_as_client_bad_port(self, host):
        port = None
        with pytest.raises(TypeError):
            Address.as_client(host, port)

    @pytest.mark.parametrize("host", [None, "", "localhost", "1.2.3.4"])
    @pytest.mark.parametrize("port", ["", -1, 65536])
    def test_as_client_bad_port2(self, host, port):
        with pytest.raises(ValueError):
            Address.as_client(host, port)

    @pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "::", "1.2.3.4"])
    def test_new_valid_address(self, host):
        addr = Address(host, 9786)
        assert addr == Address(host, 9786, isserver=False)

    def test_new_public_host(self):
        addr = Address("", 9786)
        assert addr == Address("", 9786, isserver=True)

    def test_new_default_host(self):
        addr = Address(None, 9786)
        assert addr == Address("localhost", 9786, isserver=True)

    def test_new_wildcard_host(self):
        addr = Address("*", 9786)
        assert addr == Address("", 9786, isserver=True)

    @pytest.mark.parametrize("host", [None, "", "localhost", "1.2.3.4"])
    def test_new_bad_port(self, host):
        port = None
        with pytest.raises(TypeError):
            Address(host, port)

    @pytest.mark.parametrize("host", [None, "", "localhost", "1.2.3.4"])
    @pytest.mark.parametrize("port", ["", -1, 65536])
    def test_new_bad_port2(self, host, port):
        with pytest.raises(ValueError):
            Address(host, port)
