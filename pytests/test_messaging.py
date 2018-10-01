# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

import json
import io
import pytest
import random
import socket
import threading
import time

from ptvsd.messaging import JsonIOStream, JsonMessageChannel, Response
from .helpers.messaging import JsonMemoryStream, LoggingJsonStream


class TestJsonIOStream(object):
    MESSAGE_BODY_TEMPLATE = u'{"arguments": {"threadId": 3}, "command": "next", "seq": %d, "type": "request"}'
    MESSAGES = []
    SERIALIZED_MESSAGES = b''

    @classmethod
    def setup_class(cls):
        for seq in range(0, 3):
            message_body = cls.MESSAGE_BODY_TEMPLATE % seq
            message = json.loads(message_body)
            message_body = message_body.encode('utf-8')
            cls.MESSAGES.append(message)
            message_header = u'Content-Length: %d\r\n\r\n' % len(message_body)
            cls.SERIALIZED_MESSAGES += message_header.encode('ascii') + message_body

    def test_read(self):
        data = io.BytesIO(self.SERIALIZED_MESSAGES)
        stream = JsonIOStream(data, data)
        for expected_message in self.MESSAGES:
            message = stream.read_json()
            assert message == expected_message
        with pytest.raises(EOFError):
            stream.read_json()

    def test_write(self):
        data = io.BytesIO()
        stream = JsonIOStream(data, data)
        for message in self.MESSAGES:
            stream.write_json(message)
        data = data.getvalue()
        assert data == self.SERIALIZED_MESSAGES


class TestJsonMemoryStream(object):
    MESSAGES = [
        {'seq': 1, 'type': 'request', 'command': 'next', 'arguments': {'threadId': 3}},
        {'seq': 2, 'type': 'request', 'command': 'next', 'arguments': {'threadId': 5}},
    ]

    def test_read(self):
        stream = JsonMemoryStream(self.MESSAGES, [])
        for expected_message in self.MESSAGES:
            message = stream.read_json()
            assert message == expected_message
        with pytest.raises(EOFError):
            stream.read_json()

    def test_write(self):
        messages = []
        stream = JsonMemoryStream([], messages)
        for message in self.MESSAGES:
            stream.write_json(message)
        assert messages == self.MESSAGES


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
            {'seq': 1, 'type': 'event', 'event': 'stopped', 'body': {'reason': 'pause'}},
            {'seq': 2, 'type': 'event', 'event': 'unknown', 'body': {'something': 'else'}},
        ]

        events_received = []

        class Handlers(object):
            def stopped_event(self, channel, body):
                events_received.append((channel, body))

            def event(self, channel, event, body):
                events_received.append((channel, event, body))

        input, input_exhausted = self.iter_with_event(EVENTS)
        stream = LoggingJsonStream(JsonMemoryStream(input, []))
        channel = JsonMessageChannel(stream, Handlers())
        channel.start()
        input_exhausted.wait()

        assert events_received == [
            (channel, EVENTS[0]['body']),
            (channel, 'unknown', EVENTS[1]['body']),
        ]

    def test_requests(self):
        REQUESTS = [
            {'seq': 1, 'type': 'request', 'command': 'next', 'arguments': {'threadId': 3}},
            {'seq': 2, 'type': 'request', 'command': 'unknown', 'arguments': {'answer': 42}},
            {'seq': 3, 'type': 'request', 'command': 'pause', 'arguments': {'threadId': 5}},
        ]

        requests_received = []

        class Handlers(object):
            def next_request(self, channel, arguments):
                requests_received.append((channel, arguments))
                return {'threadId': 7}

            def request(self, channel, command, arguments):
                requests_received.append((channel, command, arguments))

            def pause_request(self, channel, arguments):
                requests_received.append((channel, arguments))
                raise RuntimeError('pause error')

        input, input_exhausted = self.iter_with_event(REQUESTS)
        output = []
        stream = LoggingJsonStream(JsonMemoryStream(input, output))
        channel = JsonMessageChannel(stream, Handlers())
        channel.start()
        input_exhausted.wait()

        assert requests_received == [
            (channel, REQUESTS[0]['arguments']),
            (channel, 'unknown', REQUESTS[1]['arguments']),
            (channel, REQUESTS[2]['arguments']),
        ]

        assert output == [
            {'seq': 1, 'type': 'response', 'request_seq': 1, 'command': 'next', 'success': True, 'body': {'threadId': 7}},
            {'seq': 2, 'type': 'response', 'request_seq': 2, 'command': 'unknown', 'success': True},
            {'seq': 3, 'type': 'response', 'request_seq': 3, 'command': 'pause', 'success': False, 'message': 'pause error'},
        ]

    def test_responses(self):
        request1_sent = threading.Event()
        request2_sent = threading.Event()
        request3_sent = threading.Event()

        def iter_responses():
            request1_sent.wait()
            yield {'seq': 1, 'type': 'response', 'request_seq': 1, 'command': 'next', 'success': True, 'body': {'threadId': 3}}
            request2_sent.wait()
            yield {'seq': 2, 'type': 'response', 'request_seq': 2, 'command': 'pause', 'success': False, 'message': 'pause error'}
            request3_sent.wait()
            yield {'seq': 3, 'type': 'response', 'request_seq': 3, 'command': 'next', 'success': True, 'body': {'threadId': 5}}

        stream = LoggingJsonStream(JsonMemoryStream(iter_responses(), []))
        channel = JsonMessageChannel(stream, None)
        channel.start()

        # Blocking wait.
        request1 = channel.send_request('next')
        request1_sent.set()
        response1 = request1.wait_for_response()
        assert response1 == Response(True, 'next', body={'threadId': 3})

        # Async callback, registered before response is received.
        request2 = channel.send_request('pause')
        response2 = [None]
        response2_received = threading.Event()
        def response2_handler(response):
            response2[0] = response
            response2_received.set()
        request2.on_response(response2_handler)
        request2_sent.set()
        response2_received.wait()
        assert response2[0] == Response(False, 'pause', error_message='pause error')

        # Async callback, registered after response is received.
        request3 = channel.send_request('next')
        request3_sent.set()
        request3.wait_for_response()
        response3 = [None]
        response3_received = threading.Event()
        def response3_handler(response):
            response3[0] = response
            response3_received.set()
        request3.on_response(response3_handler)
        response3_received.wait()
        assert response3[0] == Response(True, 'next', body={'threadId': 5})

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

            def start(self, channel):
                self._worker = threading.Thread(name=self.name, target=lambda: self._send_requests_and_events(channel))
                self._worker.daemon = True
                self._worker.start()

            def wait(self):
                self._worker.join()

            def fizz_event(self, channel, body):
                with self.lock:
                    self.received.append(('event', 'fizz', body))

            def buzz_event(self, channel, body):
                with self.lock:
                    self.received.append(('event', 'buzz', body))

            def event(self, channel, event, body):
                with self.lock:
                    self.received.append(('event', event, body))

            def make_and_log_response(self, command):
                x = random.randint(-100, 100)
                if x >= 0:
                    response = Response(True, command, body=x)
                else:
                    response = Response(False, command, error_message=str(x))
                with self.lock:
                    self.responses_sent.append(response)
                if response.success:
                    return x
                else:
                    raise RuntimeError(response.error_message)

            def fizz_request(self, channel, arguments):
                with self.lock:
                    self.received.append(('request', 'fizz', arguments))
                return self.make_and_log_response('fizz')

            def buzz_request(self, channel, arguments):
                with self.lock:
                    self.received.append(('request', 'buzz', arguments))
                return self.make_and_log_response('buzz')

            def request(self, channel, command, arguments):
                with self.lock:
                    self.received.append(('request', command, arguments))
                return self.make_and_log_response(command)

            def _send_requests_and_events(self, channel):
                pending_requests = [0]
                for _ in range(0, 100):
                    typ = random.choice(('event', 'request'))
                    name = random.choice(('fizz', 'buzz', 'fizzbuzz'))
                    body = random.randint(0, 100)
                    with self.lock:
                        self.sent.append((typ, name, body))
                    if typ == 'event':
                        channel.send_event(name, body)
                    elif typ == 'request':
                        with self.lock:
                            pending_requests[0] += 1
                        req = channel.send_request(name, body)
                        def response_handler(response):
                            with self.lock:
                                self.responses_received.append(response)
                                pending_requests[0] -= 1
                        req.on_response(response_handler)
                # Spin until we get responses to all requests.
                while True:
                    with self.lock:
                        if pending_requests[0] == 0:
                            break
                    time.sleep(0.1)

        fuzzer1 = Fuzzer('fuzzer1')
        fuzzer2 = Fuzzer('fuzzer2')

        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.bind(('localhost', 0))
        _, port = server_socket.getsockname()
        server_socket.listen(0)

        socket1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        socket1_thread = threading.Thread(target=lambda: socket1.connect(('localhost', port)))
        socket1_thread.start()
        socket2, _ = server_socket.accept()
        socket1_thread.join()

        try:
            io1 = socket1.makefile('rwb', 0)
            io2 = socket2.makefile('rwb', 0)

            stream1 = LoggingJsonStream(JsonIOStream(io1, io1))
            channel1 = JsonMessageChannel(stream1, fuzzer1)
            channel1.start()
            fuzzer1.start(channel1)

            stream2 = LoggingJsonStream(JsonIOStream(io2, io2))
            channel2 = JsonMessageChannel(stream2, fuzzer2)
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

