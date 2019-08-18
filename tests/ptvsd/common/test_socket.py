# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import platform
import pytest
from ptvsd.common import sockets


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
        sock1 = sockets.create_server(self.HOST1, 0)
        try:
            _, PORT1 = sock1.getsockname()
            with pytest.raises(Exception):
                sockets.create_server(self.HOST1, PORT1)
        finally:
            sockets.close_socket(sock1)

    def test_reuse_same_port(self):
        try:
            sock1, sock2 = None, None
            sock1 = sockets.create_server(self.HOST1, 0)
            _, PORT1 = sock1.getsockname()
            sock2 = sockets.create_server(self.HOST2, PORT1)
            assert sock1.getsockname() == (self.HOST1, PORT1)
            assert sock2.getsockname() == (self.HOST2, PORT1)
        except Exception:
            pytest.fail()
        finally:
            if sock1 is not None:
                sockets.close_socket(sock1)
            if sock2 is not None:
                sockets.close_socket(sock2)
