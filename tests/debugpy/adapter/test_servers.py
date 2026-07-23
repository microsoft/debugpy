# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import threading

from debugpy import adapter
from debugpy.adapter import servers, sessions


class FakeMessage:
    def __init__(self, values):
        self.values = values

    def __call__(self, name, _validator, optional=False):
        if optional and name not in self.values:
            return ()
        return self.values[name]


class FakeStream:
    name = "fake stream"


class FakeChannel:
    def __init__(self, stream, handlers, pid):
        self.stream = stream
        self.handlers = handlers
        self.pid = pid
        self.name = "fake channel"
        self.closed = False

    def start(self):
        pass

    def request(self, command, arguments=None):
        assert command == "pydevdSystemInfo"
        return FakeMessage(
            {
                "process": FakeMessage(
                    {
                        "pid": self.pid,
                    }
                )
            }
        )

    def close(self):
        self.closed = True


def test_connection_waits_for_actual_session_attachment(monkeypatch):
    # Regression test for a race in Connection.__init__: once a connection is
    # published to servers._connections, another thread can attach it to a
    # session before the constructor classifies it. The constructor must not
    # then close the channel as an "unexpected replacement". Without the fix in
    # servers.py, this test fails (the channel is closed / the constructor never
    # reaches the post-attachment check).
    pid = 1234
    stream = FakeStream()
    channel = FakeChannel(stream, None, pid)
    attached_session = sessions.Session()
    stale_session = sessions.Session()
    stale_session.pid = pid
    published = threading.Event()
    attachment_started = threading.Event()
    release_attachment = threading.Event()
    classification_waiting = threading.Event()
    connection_finished = threading.Event()
    connections = []
    attach_errors = []
    connection_errors = []
    original_server = servers.Server

    class ObservedLock:
        def __init__(self):
            self._lock = threading.RLock()

        def __enter__(self):
            if published.is_set() and threading.current_thread().name == "connection":
                classification_waiting.set()
            self._lock.acquire()
            return self

        def __exit__(self, *_):
            self._lock.release()

    class ConnectionPublished:
        def set(self):
            published.set()

    def blocking_server(session, connection):
        attachment_started.set()
        assert release_attachment.wait(5)
        return original_server(session, connection)

    def attach_published_connection():
        try:
            assert published.wait(5)
            with servers._lock:
                connection = servers._connections[-1]
            connection.attach_to_session(attached_session)
        except Exception as exc:
            attach_errors.append(exc)

    def create_connection():
        try:
            connections.append(servers.Connection(object()))
        except Exception as exc:
            connection_errors.append(exc)
        finally:
            connection_finished.set()

    def get_session(candidate_pid):
        if candidate_pid != pid:
            return None
        assert attachment_started.wait(5)
        return stale_session

    monkeypatch.setattr(adapter, "access_token", None)
    monkeypatch.setattr(servers, "access_token", None)
    monkeypatch.setattr(servers, "_lock", ObservedLock())
    monkeypatch.setattr(servers, "_connections", [])
    monkeypatch.setattr(servers, "_connections_changed", ConnectionPublished())
    monkeypatch.setattr(servers, "Server", blocking_server)
    monkeypatch.setattr(
        servers.messaging.JsonIOStream, "from_socket", lambda *_: stream
    )
    monkeypatch.setattr(
        servers.messaging,
        "JsonMessageChannel",
        lambda *_: channel,
    )
    monkeypatch.setattr(sessions, "get", get_session)

    attach_thread = threading.Thread(target=attach_published_connection, daemon=True)
    connection_thread = threading.Thread(
        target=create_connection,
        name="connection",
        daemon=True,
    )
    attach_thread.start()
    connection_thread.start()
    try:
        assert attachment_started.wait(5)
        assert classification_waiting.wait(5)
        assert not connection_finished.is_set()
    finally:
        release_attachment.set()
        attach_thread.join(5)
        connection_thread.join(5)

    assert not attach_thread.is_alive()
    assert not connection_thread.is_alive()
    assert not attach_errors
    assert not connection_errors
    assert len(connections) == 1
    assert connections[0].server is attached_session.server
    assert not channel.closed
