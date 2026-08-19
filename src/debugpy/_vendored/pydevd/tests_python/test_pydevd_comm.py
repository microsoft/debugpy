from unittest import mock

import pytest

from _pydevd_bundle import pydevd_comm


def start_client(monkeypatch, sock):
    monkeypatch.setattr(pydevd_comm, "socket", mock.Mock(return_value=sock))
    monkeypatch.setattr(
        pydevd_comm.socket_module,
        "getaddrinfo",
        lambda *_: [(pydevd_comm.AF_INET, pydevd_comm.SOCK_STREAM, 0, "", ("127.0.0.1", 5678))],
    )
    assert pydevd_comm.start_client("localhost", 5678) is sock
    sock.connect.assert_called_once_with(("localhost", 5678))


def test_start_client_sets_tcp_nodelay(monkeypatch):
    sock = mock.Mock()
    monkeypatch.setattr(pydevd_comm.socket_module, "TCP_NODELAY", mock.sentinel.tcp_nodelay)

    start_client(monkeypatch, sock)
    sock.setsockopt.assert_any_call(pydevd_comm.socket_module.IPPROTO_TCP, mock.sentinel.tcp_nodelay, 1)


@pytest.mark.parametrize("error", [AttributeError, OSError])
def test_start_client_ignores_tcp_nodelay_error(monkeypatch, error):
    sock = mock.Mock()
    sock.setsockopt.side_effect = error
    monkeypatch.setattr(pydevd_comm.socket_module, "TCP_NODELAY", mock.sentinel.tcp_nodelay)

    start_client(monkeypatch, sock)
    sock.setsockopt.assert_any_call(pydevd_comm.socket_module.IPPROTO_TCP, mock.sentinel.tcp_nodelay, 1)


def test_start_server_sets_tcp_nodelay(monkeypatch):
    server, accepted = mock.Mock(), mock.Mock()
    address = ("127.0.0.1", 5678)
    server.configure_mock(**{"accept.return_value": (accepted, address), "getsockname.return_value": address})
    monkeypatch.setattr(pydevd_comm, "create_server_socket", mock.Mock(return_value=server))
    monkeypatch.setattr(pydevd_comm.socket_module, "TCP_NODELAY", mock.sentinel.tcp_nodelay)
    assert pydevd_comm.start_server(0) is accepted
    accepted.setsockopt.assert_called_once_with(pydevd_comm.socket_module.IPPROTO_TCP, mock.sentinel.tcp_nodelay, 1)


@pytest.mark.parametrize("error", [AttributeError, OSError])
def test_start_server_ignores_tcp_nodelay_error(monkeypatch, error):
    server, accepted = mock.Mock(), mock.Mock()
    address = ("127.0.0.1", 5678)
    server.configure_mock(**{"accept.return_value": (accepted, address), "getsockname.return_value": address})
    accepted.setsockopt.side_effect = error
    monkeypatch.setattr(pydevd_comm, "create_server_socket", mock.Mock(return_value=server))
    monkeypatch.setattr(pydevd_comm.socket_module, "TCP_NODELAY", mock.sentinel.tcp_nodelay)

    assert pydevd_comm.start_server(0) is accepted
    accepted.setsockopt.assert_called_once_with(pydevd_comm.socket_module.IPPROTO_TCP, mock.sentinel.tcp_nodelay, 1)
