# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

"""Unit tests for debugpy.adapter.clients message handlers."""

import pytest

from debugpy.common import json, messaging
from debugpy.adapter import clients


class _MemoryStream(object):
    """Minimal in-memory JSON stream that records everything written to it."""

    json_encoder_factory = messaging.JsonIOStream.json_encoder_factory

    def __init__(self):
        self.name = "memory"
        self.output = []

    def close(self):
        pass

    def write_json(self, value, encoder=None):
        encoder = encoder if encoder is not None else self.json_encoder_factory()
        self.output.append(json.loads(encoder.encode(value)))


class _FakeSession(object):
    """Stands in for the reentrant session lock used by the message_handler wrapper."""

    def __init__(self, server=None):
        self.server = server

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


class _UnpropagatingChannel(object):
    def propagate(self, request):
        return None


class _FakeServer(object):
    channel = _UnpropagatingChannel()


def _make_client(start_request, has_started):
    stream = _MemoryStream()
    channel = messaging.JsonMessageChannel(stream, None)

    client = clients.Client.__new__(clients.Client)
    client.session = _FakeSession()
    client.start_request = start_request
    client.has_started = has_started

    request = messaging.Request(channel, 1, "configurationDone", {})
    return client, request, stream


@pytest.mark.parametrize(
    "start_request, has_started, scenario",
    [
        (None, False, "before a start request"),
        (object(), True, "after startup has already begun"),
    ],
)
def test_configuration_done_out_of_order_is_rejected(start_request, has_started, scenario):
    client, request, stream = _make_client(start_request, has_started)

    # The guard must fail the request loudly rather than silently falling through
    # and delegating to the server (the previously ineffective guard did the latter).
    with pytest.raises(messaging.MessageHandlingError):
        clients.Client.configurationDone_request(client, request)

    (response,) = stream.output
    assert response["type"] == "response"
    assert response["command"] == "configurationDone"
    assert response["success"] is False
    assert response["message"] == (
        '"configurationDone" is only allowed during handling of a "launch" '
        'or an "attach" request'
    )
    # The guard must run before any startup side effects.
    assert client.has_started is has_started


def test_evaluate_request_that_cannot_be_propagated_is_rejected():
    stream = _MemoryStream()
    channel = messaging.JsonMessageChannel(stream, None)

    client = clients.Client.__new__(clients.Client)
    client.session = _FakeSession(_FakeServer())
    request = messaging.Request(channel, 1, "evaluate", {})

    with pytest.raises(
        messaging.MessageHandlingError,
        match='"evaluate" could not be propagated to the debug server',
    ):
        clients.Client.evaluate_request(client, request)

    (response,) = stream.output
    assert response == {
        "seq": 1,
        "type": "response",
        "request_seq": 1,
        "success": False,
        "command": "evaluate",
        "message": '"evaluate" could not be propagated to the debug server',
    }
