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
    def __init__(self, stream, pid):
        self.stream = stream
        self.handlers = None
        self.pid = pid
        self.name = "fake channel"
        self.closed = False

    def start(self):
        pass

    def request(self, command, arguments=None):
        assert command == "pydevdSystemInfo"
        return FakeMessage({"process": FakeMessage({"pid": self.pid})})

    def close(self):
        self.closed = True


def test_connection_waits_for_actual_session_attachment(monkeypatch):
    # Attaching a connection stamps session.pid with the connection's pid, so a
    # connection attached in the window after publication but before __init__
    # classifies it by pid must survive classification rather than be closed.
    pid = 1234
    stream = FakeStream()
    channel = FakeChannel(stream, pid)
    session = sessions.Session()
    attachment_complete = threading.Event()
    connections = []
    errors = []

    def attach_like_a_client():
        # Mirror the real client attach path.
        try:
            conn = servers.wait_for_connection(
                session, lambda c: c.pid == pid, timeout=None
            )
            conn.attach_to_session(session)
        except Exception as exc:
            errors.append(exc)
        finally:
            attachment_complete.set()

    def create_connection():
        try:
            connections.append(servers.Connection(object()))
        except Exception as exc:
            errors.append(exc)

    def get_session(candidate_pid):
        if candidate_pid != pid:
            return None
        # Block classification until the attach completes, forcing the race.
        assert attachment_complete.wait(5)
        return session

    monkeypatch.setattr(adapter, "access_token", None)
    monkeypatch.setattr(servers, "access_token", None)
    monkeypatch.setattr(servers, "_connections", [])
    monkeypatch.setattr(servers, "_connections_changed", threading.Event())
    monkeypatch.setattr(
        servers.messaging.JsonIOStream, "from_socket", lambda *_: stream
    )
    monkeypatch.setattr(servers.messaging, "JsonMessageChannel", lambda *_: channel)
    monkeypatch.setattr(sessions, "get", get_session)

    attach_thread = threading.Thread(target=attach_like_a_client, daemon=True)
    connection_thread = threading.Thread(target=create_connection, daemon=True)
    attach_thread.start()
    connection_thread.start()
    attach_thread.join(5)
    connection_thread.join(5)

    assert not attach_thread.is_alive()
    assert not connection_thread.is_alive()
    assert not errors
    assert len(connections) == 1
    assert connections[0].server is session.server
    assert not channel.closed
