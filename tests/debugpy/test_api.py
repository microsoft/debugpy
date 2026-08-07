import pytest

import debugpy.server.api as _api


@pytest.fixture
def no_settrace(monkeypatch):
    # Avoid actually starting pydevd; we only care about listen()'s return value.
    monkeypatch.setattr(_api, "_settrace", lambda **kwargs: None)
    monkeypatch.setattr(_api.listen, "called", False)


def test_listen_in_process_returns_endpoint(no_settrace):
    # Regression test for #1656: listen(..., in_process_debug_adapter=True) used
    # to return None, unlike the out-of-process path which returns (host, port).
    endpoint = _api.listen(("127.0.0.1", 5678), in_process_debug_adapter=True)
    assert endpoint == ("127.0.0.1", 5678)
    assert _api.listen.called is True


class _FakePyDB:
    """Minimal stand-in for the global pydevd debugger.

    Mirrors the bits of the real PyDB that listen()'s in-process path reads
    after _settrace(): ``wait_for_server_socket_ready`` and
    ``_server_socket_name`` (set by the reader thread once the listening
    socket is bound).
    """

    def __init__(self, host, port):
        self._server_socket_name = (host, port)

    def wait_for_server_socket_ready(self):
        return None


@pytest.fixture
def in_process_debugger(monkeypatch):
    # Stub out _settrace (don't actually start pydevd) and inject a fake
    # global debugger so that listen()'s in-process path can read the
    # actual bound endpoint back from it.
    monkeypatch.setattr(_api, "_settrace", lambda **kwargs: None)
    monkeypatch.setattr(_api.listen, "called", False)
    fake = _FakePyDB("127.0.0.1", 54321)
    monkeypatch.setattr(_api, "get_global_debugger", lambda: fake)
    return fake


def test_listen_in_process_port_zero_resolves_bound_port(in_process_debugger):
    # Regression test for #1656: when port=0 is passed, listen() must return
    # the OS-assigned bound port rather than the literal 0.
    endpoint = _api.listen(("127.0.0.1", 0), in_process_debug_adapter=True)
    host, port = endpoint
    assert host == "127.0.0.1"
    assert isinstance(port, int)
    assert port > 0
    assert port == in_process_debugger._server_socket_name[1]
