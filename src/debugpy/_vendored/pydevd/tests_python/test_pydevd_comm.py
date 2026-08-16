from unittest import mock

from _pydevd_bundle import pydevd_comm


def start_client(monkeypatch, sock):
    monkeypatch.setattr(pydevd_comm, "socket", lambda *_: sock)
    monkeypatch.setattr(pydevd_comm.socket_module, "getaddrinfo", lambda *_: [])
    return pydevd_comm.start_client("localhost", 5678)


def test_start_client_sets_tcp_nodelay(monkeypatch):
    sock = mock.Mock()
    tcp_nodelay = mock.sentinel.tcp_nodelay
    monkeypatch.setattr(pydevd_comm.socket_module, "TCP_NODELAY", tcp_nodelay)

    assert start_client(monkeypatch, sock) is sock
    sock.setsockopt.assert_any_call(
        pydevd_comm.socket_module.IPPROTO_TCP,
        tcp_nodelay,
        1,
    )


def test_start_client_without_tcp_nodelay(monkeypatch):
    sock = mock.Mock()
    monkeypatch.delattr(pydevd_comm.socket_module, "TCP_NODELAY", raising=False)

    assert start_client(monkeypatch, sock) is sock


def test_start_client_ignores_tcp_nodelay_error(monkeypatch):
    sock = mock.Mock()
    tcp_nodelay = mock.sentinel.tcp_nodelay
    monkeypatch.setattr(pydevd_comm.socket_module, "TCP_NODELAY", tcp_nodelay)

    def set_option(_level, option, _value):
        if option is tcp_nodelay:
            raise OSError

    sock.setsockopt.side_effect = set_option

    assert start_client(monkeypatch, sock) is sock
