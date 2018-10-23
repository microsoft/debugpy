# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import pytest
from ptvsd.socket import create_server, close_socket


class TestSocketServerReuse(object):
    HOST1 = '127.0.0.1'
    HOST2 = '127.0.0.2'
    PORT1 = 7890

    def test_reuse_same_address_port(self):
        try:
            sock1 = create_server(self.HOST1, self.PORT1)
            with pytest.raises(Exception):
                create_server(self.HOST1, self.PORT1)
            assert sock1.getsockname() == (self.HOST1, self.PORT1)
        finally:
            close_socket(sock1)

    def test_reuse_same_port(self):
        try:
            sock1 = create_server(self.HOST1, self.PORT1)
            sock2 = create_server(self.HOST2, self.PORT1)
            assert sock1.getsockname() == (self.HOST1, self.PORT1)
            assert sock2.getsockname() == (self.HOST2, self.PORT1)
        finally:
            close_socket(sock1)
            close_socket(sock2)
