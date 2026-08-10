# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

"""Unit tests for debugpy.server.api behaviors that don't require a live session."""

import subprocess

import pytest

from debugpy.server import api


class _FakeSockIO:
    def __init__(self, data):
        self._data = data

    def read(self):
        return self._data

    def close(self):
        pass


class _FakeSocket:
    def __init__(self, data):
        self._data = data

    def settimeout(self, timeout):
        pass

    def makefile(self, *args, **kwargs):
        return _FakeSockIO(self._data)


class _FakeEndpointsListener:
    def __init__(self, data):
        self._data = data

    def accept(self):
        return _FakeSocket(self._data), None

    def close(self):
        pass


class _FakeAdapterProcess:
    pid = 4321
    returncode = None

    def wait(self):
        pass


def _stub_listen_environment(monkeypatch, adapter_data):
    """Drive `listen()` up to reading the adapter endpoints without real I/O."""

    # `listen()` is single-shot; reset the latch so the test can invoke it.
    monkeypatch.setattr(api.listen, "called", False, raising=False)
    monkeypatch.setattr(api, "ensure_logging", lambda: None)

    listener = _FakeEndpointsListener(adapter_data)
    monkeypatch.setattr(api.sockets, "create_server", lambda *a, **k: listener)
    monkeypatch.setattr(api.sockets, "get_address", lambda _l: ("127.0.0.1", 12345))
    monkeypatch.setattr(api.sockets, "close_socket", lambda _s: None)

    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: _FakeAdapterProcess())
    monkeypatch.setattr(api.pydevd, "add_dont_terminate_child_pid", lambda _pid: None)


def test_listen_empty_adapter_read_raises(monkeypatch):
    # An empty read from the adapter endpoints socket is EOF: `sock_io.read()`
    # returns b"" (not None) at EOF, so the `if not data:` guard must fire and
    # surface an EOFError rather than falling through to json.loads (which would
    # raise a confusing JSONDecodeError on empty input).
    _stub_listen_environment(monkeypatch, b"")

    with pytest.raises(RuntimeError) as exc_info:
        api.listen(("127.0.0.1", 0))

    assert (
        str(exc_info.value)
        == "error retrieving adapter endpoints: EOF while reading adapter endpoints"
    )
