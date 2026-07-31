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
