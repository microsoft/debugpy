# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

"""Tests for JSON message streams and channels.
"""

import collections
import functools
import io
import pytest
import random
import re
import socket
import threading
import time

from debugpy.common import json, log, messaging
from tests.patterns import some


# Default timeout for tests in this file.
pytestmark = pytest.mark.timeout(5)


class JsonMemoryStream(object):
    """Like JsonIOStream, but working directly with values stored in memory.
    Values are round-tripped through JSON serialization.

    For input, values are read from the supplied sequence or iterator.
    For output, values are appended to the supplied collection.
    """

    json_decoder_factory = messaging.JsonIOStream.json_decoder_factory
    json_encoder_factory = messaging.JsonIOStream.json_encoder_factory

    def __init__(self, input, output, name="memory"):
        self.name = name
        self.input = iter(input)
        self.output = output

    def close(self):
        pass

    def _log_message(self, dir, data):
        format_string = "{0} {1} " + (
            "{2:indent=None}" if isinstance(data, list) else "{2}"
        )
        return log.debug(format_string, self.name, dir, json.repr(data))

    def read_json(self, decoder=None):
        decoder = decoder if decoder is not None else self.json_decoder_factory()
        try:
            value = next(self.input)
        except StopIteration:
            raise messaging.NoMoreMessages(stream=self)
        value = decoder.decode(json.dumps(value))
        self._log_message("-->", value)
        return value

    def write_json(self, value, encoder=None):
        encoder = encoder if encoder is not None else self.json_encoder_factory()
        value = json.loads(encoder.encode(value))
        self._log_message("<--", value)
        self.output.append(value)


class TestJsonIOStream(object):
    MESSAGE_BODY_TEMPLATE = '{"arguments": {"threadId": 3}, "command": "next", "seq": %d, "type": "request"}'
    MESSAGES = []
    SERIALIZED_MESSAGES = b""

    @classmethod
    def setup_class(cls):
        for seq in range(0, 3):
            message_body = cls.MESSAGE_BODY_TEMPLATE % seq
            message = json.loads(
                message_body, object_pairs_hook=collections.OrderedDict
            )
            message_body = message_body.encode("utf-8")
            cls.MESSAGES.append(message)
            message_header = "Content-Length: %d\r\n\r\n" % len(message_body)
            cls.SERIALIZED_MESSAGES += message_header.encode("ascii") + message_body

    def test_read(self):
        data = io.BytesIO(self.SERIALIZED_MESSAGES)
        stream = messaging.JsonIOStream(data, data, "data")
        for expected_message in self.MESSAGES:
            message = stream.read_json()
            assert message == expected_message
        with pytest.raises(messaging.NoMoreMessages) as exc_info:
            stream.read_json()
        assert exc_info.value.stream is stream

    def test_write(self):
        data = io.BytesIO()
        stream = messaging.JsonIOStream(data, data, "data")
        for message in self.MESSAGES:
            stream.write_json(message)
        data = data.getvalue()
        assert data == self.SERIALIZED_MESSAGES


class TestJsonMemoryStream(object):
    MESSAGES = [
        {"seq": 1, "type": "request", "command": "next", "arguments": {"threadId": 3}},
        {"seq": 2, "type": "request", "command": "next", "arguments": {"threadId": 5}},
    ]

    def test_read(self):
        stream = JsonMemoryStream(self.MESSAGES, [])
        for expected_message in self.MESSAGES:
            message = stream.read_json()
            assert message == expected_message
        with pytest.raises(messaging.NoMoreMessages) as exc_info:
            stream.read_json()
        assert exc_info.value.stream is stream

    def test_write(self):
        messages = []
        stream = JsonMemoryStream([], messages)
        for message in self.MESSAGES:
            stream.write_json(message)
        assert messages == self.MESSAGES


class MessageHandlerRecorder(list):
    def __call__(self, handler):
        @functools.wraps(handler)
        def record_and_handle(instance, message):
            name = handler.__name__
            if isinstance(name, bytes):
                name = name.decode("utf-8")
            record = {"channel": message.channel, "handler": name}

            if isinstance(message, messaging.Event):
                record.update(
                    {"type": "event", "event": message.event, "body": message.body}
                )
            elif isinstance(message, messaging.Request):
                record.update(
                    {
                        "type": "request",
                        "command": message.command,
                        "arguments": message.arguments,
                    }
                )

            self.append(record)
            return handler(instance, message)

        return record_and_handle

    def expect(self, channel, inputs, handlers):
        expected_records = []
        for input, handler in zip(inputs, handlers):
            expected_record = {"channel": channel, "handler": handler}
            expected_record.update(
                {
                    key: value
                    for key, value in input.items()
                    if key in ("type", "event", "command", "body", "arguments")
                }
            )
            expected_records.append(expected_record)
        assert expected_records == self


class TestJsonMessageChannel(object):
    @staticmethod
    def iter_with_event(collection):
        """Like iter(), but also exposes a threading.Event that is set
        when the returned iterator is exhausted.
        """
        exhausted = threading.Event()

        def iterate():
            for x in collection:
                yield x
            exhausted.set()

        return iterate(), exhausted

    def test_events(self):
        EVENTS = [
            {
                "seq": 1,
                "type": "event",
                "event": "stopped",
                "body": {"reason": "pause"},
            },
            {
                "seq": 2,
                "type": "event",
                "event": "unknown",
                "body": {"something": "else"},
            },
        ]

        recorder = MessageHandlerRecorder()

        class Handlers(object):
            @recorder
            def stopped_event(self, event):
                assert event.event == "stopped"

            @recorder
            def event(self, event):
                assert event.event == "unknown"

        stream = JsonMemoryStream(EVENTS, [])
        channel = messaging.JsonMessageChannel(stream, Handlers())
        channel.start()
        channel.wait()

        recorder.expect(channel, EVENTS, ["stopped_event", "event"])

    def test_requests(self):
        REQUESTS = [
            {
                "seq": 1,
                "type": "request",
                "command": "next",
                "arguments": {"threadId": 3},
            },
            {
                "seq": 2,
                "type": "request",
                "command": "launch",
                "arguments": {"program": "main.py"},
            },
            {
                "seq": 3,
                "type": "request",
                "command": "unknown",
                "arguments": {"answer": 42},
            },
            {
                "seq": 4,
                "type": "request",
                "command": "pause",
                "arguments": {"threadId": 5},
            },
        ]

        recorder = MessageHandlerRecorder()

        class Handlers(object):
            @recorder
            def next_request(self, request):
                assert request.command == "next"
                return {"threadId": 7}

            @recorder
            def launch_request(self, request):
                assert request.command == "launch"
                self._launch = request
                return messaging.NO_RESPONSE

            @recorder
            def request(self, request):
                request.respond({})

            @recorder
            def pause_request(self, request):
                assert request.command == "pause"
                self._launch.respond({"processId": 9})
                raise request.cant_handle("pause error")

        stream = JsonMemoryStream(REQUESTS, [])
        channel = messaging.JsonMessageChannel(stream, Handlers())
        channel.start()
        channel.wait()

        recorder.expect(
            channel,
            REQUESTS,
            ["next_request", "launch_request", "request", "pause_request"],
        )

        assert stream.output == [
            {
                "seq": 1,
                "type": "response",
                "request_seq": 1,
                "command": "next",
                "success": True,
                "body": {"threadId": 7},
            },
            {
                "seq": 2,
                "type": "response",
                "request_seq": 3,
                "command": "unknown",
                "success": True,
            },
            {
                "seq": 3,
                "type": "response",
                "request_seq": 2,
                "command": "launch",
                "success": True,
                "body": {"processId": 9},
            },
            {
                "seq": 4,
                "type": "response",
                "request_seq": 4,
                "command": "pause",
                "success": False,
                "message": "pause error",
            },
        ]

    def test_responses(self):
        request1_sent = threading.Event()
        request2_sent = threading.Event()
        request3_sent = threading.Event()
        request4_sent = threading.Event()

        def iter_responses():
            request1_sent.wait()
            yield {
                "seq": 1,
                "type": "response",
                "request_seq": 1,
                "command": "next",
                "success": True,
                "body": {"threadId": 3},
            }

            request2_sent.wait()
            yield {
                "seq": 2,
                "type": "response",
                "request_seq": 2,
                "command": "pause",
                "success": False,
                "message": "Invalid message: pause not supported",
            }

            request3_sent.wait()
            yield {
                "seq": 3,
                "type": "response",
                "request_seq": 3,
                "command": "next",
                "success": True,
                "body": {"threadId": 5},
            }

            request4_sent.wait()

        stream = JsonMemoryStream(iter_responses(), [])
        channel = messaging.JsonMessageChannel(stream, None)
        channel.start()

        # Blocking wait.
        request1 = channel.send_request("next")
        request1_sent.set()
        log.info("Waiting for response...")
        response1_body = request1.wait_for_response()
        response1 = request1.response

        assert response1.success
        assert response1.request is request1
        assert response1.body == response1_body
        assert response1.body == {"threadId": 3}

        # Async callback, registered before response is received.
        request2 = channel.send_request("pause")
        response2 = []
        response2_received = threading.Event()

        def response2_handler(resp):
            response2.append(resp)
            response2_received.set()

        log.info("Registering callback")
        request2.on_response(response2_handler)
        request2_sent.set()

        log.info("Waiting for callback...")
        response2_received.wait()
        (response2,) = response2

        assert not response2.success
        assert response2.request is request2
        assert response2 is request2.response
        assert response2.body == messaging.InvalidMessageError(
            "pause not supported", request2
        )

        # Async callback, registered after response is received.
        request3 = channel.send_request("next")
        request3_sent.set()
        request3.wait_for_response()
        response3 = []
        response3_received = threading.Event()

        def response3_handler(resp):
            response3.append(resp)
            response3_received.set()

        log.info("Registering callback")
        request3.on_response(response3_handler)

        log.info("Waiting for callback...")
        response3_received.wait()
        (response3,) = response3

        assert response3.success
        assert response3.request is request3
        assert response3 is request3.response
        assert response3.body == {"threadId": 5}

        # Async callback, registered after channel is closed.
        request4 = channel.send_request("next")
        request4_sent.set()
        channel.wait()
        response4 = []
        response4_received = threading.Event()

        def response4_handler(resp):
            response4.append(resp)
            response4_received.set()

        log.info("Registering callback")
        request4.on_response(response4_handler)

        log.info("Waiting for callback...")
        response4_received.wait()
        (response4,) = response4

        assert not response4.success
        assert response4.request is request4
        assert response4 is request4.response
        assert isinstance(response4.body, messaging.NoMoreMessages)

    def test_invalid_request_handling(self):
        REQUESTS = [
            {
                "seq": 1,
                "type": "request",
                "command": "stackTrace",
                "arguments": {"AAA": {}},
            },
            {"seq": 2, "type": "request", "command": "stackTrace", "arguments": {}},
            {"seq": 3, "type": "request", "command": "unknown", "arguments": None},
            {"seq": 4, "type": "request", "command": "pause"},
        ]

        class Handlers(object):
            def stackTrace_request(self, request):
                request.arguments["AAA"]
                request.arguments["AAA"]["BBB"]

            def request(self, request):
                request.arguments["CCC"]

            def pause_request(self, request):
                request.arguments["DDD"]

        output = []
        stream = JsonMemoryStream(REQUESTS, output)
        channel = messaging.JsonMessageChannel(stream, Handlers())
        channel.start()
        channel.wait()

        def missing_property(name):
            return some.str.matching("Invalid message:.*" + re.escape(name) + ".*")

        assert output == [
            {
                "seq": 1,
                "type": "response",
                "request_seq": 1,
                "command": "stackTrace",
                "success": False,
                "message": missing_property("BBB"),
            },
            {
                "seq": 2,
                "type": "response",
                "request_seq": 2,
                "command": "stackTrace",
                "success": False,
                "message": missing_property("AAA"),
            },
            {
                "seq": 3,
                "type": "response",
                "request_seq": 3,
                "command": "unknown",
                "success": False,
                "message": missing_property("CCC"),
            },
            {
                "seq": 4,
                "type": "response",
                "request_seq": 4,
                "command": "pause",
                "success": False,
                "message": missing_property("DDD"),
            },
        ]

    def test_fuzz(self):
        # Set up two channels over the same stream that send messages to each other
        # asynchronously, and record everything that they send and receive.
        # All records should match at the end.

        class Fuzzer(object):
            def __init__(self, name):
                self.name = name
                self.lock = threading.Lock()
                self.sent = []
                self.received = []
                self.responses_sent = []
                self.responses_received = []
                self.done = False

            def start(self, channel):
                self._worker = threading.Thread(
                    name=self.name,
                    target=lambda: self._send_requests_and_events(channel),
                )
                self._worker.daemon = True
                self._worker.start()

            def wait(self):
                self._worker.join()

            def done_event(self, event):
                with self.lock:
                    self.done = True

            def fizz_event(self, event):
                assert event.event == "fizz"
                with self.lock:
                    self.received.append(("event", "fizz", event.body))

            def buzz_event(self, event):
                assert event.event == "buzz"
                with self.lock:
                    self.received.append(("event", "buzz", event.body))

            def event(self, event):
                with self.lock:
                    self.received.append(("event", event.event, event.body))

            def make_and_log_response(self, request):
                x = random.randint(-100, 100)
                if x < 0:
                    exc_type = (
                        messaging.InvalidMessageError
                        if x % 2
                        else messaging.MessageHandlingError
                    )
                    x = exc_type(str(x), request)
                with self.lock:
                    self.responses_sent.append((request.seq, x))
                return x

            def fizz_request(self, request):
                assert request.command == "fizz"
                with self.lock:
                    self.received.append(("request", "fizz", request.arguments))
                return self.make_and_log_response(request)

            def buzz_request(self, request):
                assert request.command == "buzz"
                with self.lock:
                    self.received.append(("request", "buzz", request.arguments))
                return self.make_and_log_response(request)

            def request(self, request):
                with self.lock:
                    self.received.append(
                        ("request", request.command, request.arguments)
                    )
                return self.make_and_log_response(request)

            def _got_response(self, response):
                with self.lock:
                    self.responses_received.append(
                        (response.request.seq, response.body)
                    )

            def _send_requests_and_events(self, channel):
                types = [random.choice(("event", "request")) for _ in range(0, 100)]

                for typ in types:
                    name = random.choice(("fizz", "buzz", "fizzbuzz"))
                    body = random.randint(0, 100)

                    with self.lock:
                        self.sent.append((typ, name, body))

                    if typ == "event":
                        channel.send_event(name, body)
                    elif typ == "request":
                        req = channel.send_request(name, body)
                        req.on_response(self._got_response)

                channel.send_event("done")

                # Spin until we receive "done", and also get responses to all requests.
                requests_sent = types.count("request")
                log.info("{0} waiting for {1} responses...", self.name, requests_sent)
                while True:
                    with self.lock:
                        if self.done:
                            if requests_sent == len(self.responses_received):
                                break
                    time.sleep(0.1)

        fuzzer1 = Fuzzer("fuzzer1")
        fuzzer2 = Fuzzer("fuzzer2")

        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.bind(("localhost", 0))
        _, port = server_socket.getsockname()
        server_socket.listen(0)

        socket1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        socket1_thread = threading.Thread(
            target=lambda: socket1.connect(("localhost", port))
        )
        socket1_thread.start()
        socket2, _ = server_socket.accept()
        socket1_thread.join()

        try:
            io1 = socket1.makefile("rwb", 0)
            io2 = socket2.makefile("rwb", 0)

            stream1 = messaging.JsonIOStream(io1, io1, "socket1")
            channel1 = messaging.JsonMessageChannel(stream1, fuzzer1)
            channel1.start()
            fuzzer1.start(channel1)

            stream2 = messaging.JsonIOStream(io2, io2, "socket2")
            channel2 = messaging.JsonMessageChannel(stream2, fuzzer2)
            channel2.start()
            fuzzer2.start(channel2)

            fuzzer1.wait()
            fuzzer2.wait()

        finally:
            socket1.close()
            socket2.close()

        assert fuzzer1.sent == fuzzer2.received
        assert fuzzer2.sent == fuzzer1.received
        assert fuzzer1.responses_sent == fuzzer2.responses_received
        assert fuzzer2.responses_sent == fuzzer1.responses_received


class TestTypeConversion(object):
    def test_str_to_num(self):

        # test conversion that are expected to work
        correct_trials = [("1.0", float), ("1", int), ("1", bool)]
        for val_trial, type_trial in correct_trials:
            assert isinstance(
                json.of_type(type_trial)(val_trial), type_trial
            ), "Wrong type coversion"

        # test conversion that are not expected to work
        try:
            json.of_type(int)("1.0")
            raise ValueError("This test should have failed")
        except TypeError:
            pass
