# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

import json
import io
import pytest
import random
import re
import socket
import threading
import time

from ptvsd.common import fmt, messaging
from tests.helpers.messaging import JsonMemoryStream, LoggingJsonStream
from tests.helpers.pattern import Regex


pytestmark = pytest.mark.timeout(5)


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
        stream = messaging.JsonIOStream(data, data)
        for expected_message in self.MESSAGES:
            message = stream.read_json()
            assert message == expected_message
        with pytest.raises(EOFError):
            stream.read_json()

    def test_write(self):
        data = io.BytesIO()
        stream = messaging.JsonIOStream(data, data)
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
            def stopped_event(self, event):
                assert event.event == 'stopped'
                events_received.append((event.channel, event.body))

            def event(self, event):
                events_received.append((event.channel, event.event, event.body))

        input, input_exhausted = self.iter_with_event(EVENTS)
        stream = LoggingJsonStream(JsonMemoryStream(input, []))
        channel = messaging.JsonMessageChannel(stream, Handlers())
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
            def next_request(self, request):
                assert request.command == 'next'
                requests_received.append((request.channel, request.arguments))
                return {'threadId': 7}

            def request(self, request):
                requests_received.append((request.channel, request.command, request.arguments))
                return {}

            def pause_request(self, request):
                assert request.command == 'pause'
                requests_received.append((request.channel, request.arguments))
                request.cant_handle('pause error')

        input, input_exhausted = self.iter_with_event(REQUESTS)
        output = []
        stream = LoggingJsonStream(JsonMemoryStream(input, output))
        channel = messaging.JsonMessageChannel(stream, Handlers())
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
            yield {
                'seq': 1, 'type': 'response', 'request_seq': 1, 'command': 'next',
                'success': True, 'body': {'threadId': 3},
            }

            request2_sent.wait()
            yield {
                'seq': 2, 'type': 'response', 'request_seq': 2, 'command': 'pause',
                'success': False, 'message': 'Invalid message: pause not supported',
            }

            request3_sent.wait()
            yield {
                'seq': 3, 'type': 'response', 'request_seq': 3, 'command': 'next',
                'success': True, 'body': {'threadId': 5},
            }

        stream = LoggingJsonStream(JsonMemoryStream(iter_responses(), []))
        channel = messaging.JsonMessageChannel(stream, None)
        channel.start()

        # Blocking wait.
        request1 = channel.send_request('next')
        request1_sent.set()
        response1_body = request1.wait_for_response()
        response1 = request1.response

        assert response1.success
        assert response1.request is request1
        assert response1.body == response1_body
        assert response1.body == {'threadId': 3}

        # Async callback, registered before response is received.
        request2 = channel.send_request('pause')
        response2 = []
        response2_received = threading.Event()
        def response2_handler(resp):
            response2.append(resp)
            response2_received.set()
        request2.on_response(response2_handler)
        request2_sent.set()
        response2_received.wait()
        response2, = response2

        assert not response2.success
        assert response2.request is request2
        assert response2 is request2.response
        assert response2.body == messaging.InvalidMessageError('pause not supported', request2)

        # Async callback, registered after response is received.
        request3 = channel.send_request('next')
        request3_sent.set()
        request3.wait_for_response()
        response3 = []
        response3_received = threading.Event()
        def response3_handler(resp):
            response3.append(resp)
            response3_received.set()
        request3.on_response(response3_handler)
        response3_received.wait()
        response3, = response3

        assert response3.success
        assert response3.request is request3
        assert response3 is request3.response
        assert response3.body == {'threadId': 5}

    def test_yield(self):
        REQUESTS = [
            {'seq': 10, 'type': 'request', 'command': 'launch', 'arguments': {'noDebug': False}},
            {'seq': 20, 'type': 'request', 'command': 'setBreakpoints', 'arguments': {'main.py': 1}},
            {'seq': 30, 'type': 'event', 'event': 'expected'},
            {'seq': 40, 'type': 'request', 'command': 'launch', 'arguments': {'noDebug': True}},  # test re-entrancy
            {'seq': 50, 'type': 'request', 'command': 'setBreakpoints', 'arguments': {'main.py': 2}},
            {'seq': 60, 'type': 'event', 'event': 'unexpected'},
            {'seq': 80, 'type': 'request', 'command': 'configurationDone'},
            {'seq': 90, 'type': 'request', 'command': 'launch'},  # test handler yielding empty body
        ]

        class Handlers(object):

            received = {
                'launch': 0,
                'setBreakpoints': 0,
                'configurationDone': 0,
                'expected': 0,
                'unexpected': 0,
            }

            def launch_request(self, request):
                assert request.seq in (10, 40, 90)
                self.received['launch'] += 1

                if request.seq == 10:  # launch #1
                    assert self.received == {
                        'launch': 1,
                        'setBreakpoints': 0,
                        'configurationDone': 0,
                        'expected': 0,
                        'unexpected': 0,
                    }

                    msg = yield  # setBreakpoints #1
                    assert msg.seq == 20
                    assert self.received == {
                        'launch': 1,
                        'setBreakpoints': 1,
                        'configurationDone': 0,
                        'expected': 0,
                        'unexpected': 0,
                    }

                    msg = yield  # expected
                    assert msg.seq == 30
                    assert self.received == {
                        'launch': 1,
                        'setBreakpoints': 1,
                        'configurationDone': 0,
                        'expected': 1,
                        'unexpected': 0,
                    }

                    msg = yield  # launch #2 + nested messages
                    assert msg.seq == 40
                    assert self.received == {
                        'launch': 2,
                        'setBreakpoints': 2,
                        'configurationDone': 0,
                        'expected': 1,
                        'unexpected': 1,
                    }

                    # We should see that it failed, but no exception bubbling up here.
                    assert not msg.response.success
                    assert msg.response.body == messaging.MessageHandlingError('test failure', msg)

                    msg = yield  # configurationDone
                    assert msg.seq == 80
                    assert self.received == {
                        'launch': 2,
                        'setBreakpoints': 2,
                        'configurationDone': 1,
                        'expected': 1,
                        'unexpected': 1,
                    }

                    yield {'answer': 42}

                elif request.seq == 40:  # launch #1
                    assert self.received == {
                        'launch': 2,
                        'setBreakpoints': 1,
                        'configurationDone': 0,
                        'expected': 1,
                        'unexpected': 0,
                    }

                    msg = yield  # setBreakpoints #2
                    assert msg.seq == 50
                    assert self.received == {
                        'launch': 2,
                        'setBreakpoints': 2,
                        'configurationDone': 0,
                        'expected': 1,
                        'unexpected': 0,
                    }

                    msg = yield  # unexpected
                    assert msg.seq == 60
                    assert self.received == {
                        'launch': 2,
                        'setBreakpoints': 2,
                        'configurationDone': 0,
                        'expected': 1,
                        'unexpected': 1,
                    }

                    request.cant_handle('test failure')

                elif request.seq == 90:  # launch #3
                    assert self.received == {
                        'launch': 3,
                        'setBreakpoints': 2,
                        'configurationDone': 1,
                        'expected': 1,
                        'unexpected': 1,
                    }
                    #yield {}

            def setBreakpoints_request(self, request):
                assert request.seq in (20, 50, 70)
                self.received['setBreakpoints'] += 1
                return {'which': self.received['setBreakpoints']}

            def request(self, request):
                assert request.seq == 80
                assert request.command == 'configurationDone'
                self.received['configurationDone'] += 1
                return {}

            def expected_event(self, event):
                assert event.seq == 30
                self.received['expected'] += 1

            def event(self, event):
                assert event.seq == 60
                assert event.event == 'unexpected'
                self.received['unexpected'] += 1

        input, input_exhausted = self.iter_with_event(REQUESTS)
        output = []
        stream = LoggingJsonStream(JsonMemoryStream(input, output))
        channel = messaging.JsonMessageChannel(stream, Handlers())
        channel.start()
        input_exhausted.wait()

        assert output == [
            {
                'seq': 1, 'type': 'response', 'request_seq': 20, 'command': 'setBreakpoints',
                'success': True, 'body': {'which': 1},
            },
            {
                'seq': 2, 'type': 'response', 'request_seq': 50, 'command': 'setBreakpoints',
                'success': True, 'body': {'which': 2},
            },
            {
                'seq': 3, 'type': 'response', 'request_seq': 40, 'command': 'launch',
                'success': False, 'message': 'test failure',
            },
            {
                'seq': 4, 'type': 'response', 'request_seq': 80, 'command': 'configurationDone',
                'success': True,
            },
            {
                'seq': 5, 'type': 'response', 'request_seq': 10, 'command': 'launch',
                'success': True, 'body': {'answer': 42},
            },
            {
                'seq': 6, 'type': 'response', 'request_seq': 90, 'command': 'launch',
                'success': True,
            },
        ]

    def test_invalid_request_handling(self):
        REQUESTS = [
            {
                'seq': 1, 'type': 'request', 'command': 'stackTrace',
                'arguments': {"AAA": {}},
            },
            {'seq': 2, 'type': 'request', 'command': 'stackTrace', 'arguments': {}},
            {'seq': 3, 'type': 'request', 'command': 'unknown', 'arguments': None},
            {'seq': 4, 'type': 'request', 'command': 'pause'},
        ]

        class Handlers(object):
            def stackTrace_request(self, request):
                print(request.arguments["AAA"])
                print(request.arguments["AAA"]["BBB"])

            def request(self, request):
                print(request.arguments["CCC"])

            def pause_request(self, request):
                print(request.arguments["DDD"])

        input, input_exhausted = self.iter_with_event(REQUESTS)
        output = []
        stream = LoggingJsonStream(JsonMemoryStream(input, output))
        channel = messaging.JsonMessageChannel(stream, Handlers())
        channel.start()
        input_exhausted.wait()

        def missing_property(name):
            return Regex("^Invalid message:.*" + re.escape(name))

        assert output == [
            {
                'seq': 1, 'type': 'response', 'request_seq': 1,
                'command': 'stackTrace', 'success': False,
                'message': missing_property("BBB"),
            },
            {
                'seq': 2, 'type': 'response', 'request_seq': 2,
                'command': 'stackTrace', 'success': False,
                'message': missing_property("AAA"),
            },
            {
                'seq': 3, 'type': 'response', 'request_seq': 3,
                'command': 'unknown', 'success': False,
                'message': missing_property("CCC"),
            },
            {
                'seq': 4, 'type': 'response', 'request_seq': 4,
                'command': 'pause', 'success': False,
                'message': missing_property("DDD"),
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
                self._worker = threading.Thread(name=self.name, target=lambda: self._send_requests_and_events(channel))
                self._worker.daemon = True
                self._worker.start()

            def wait(self):
                self._worker.join()

            def done_event(self, event):
                with self.lock:
                    self.done = True

            def fizz_event(self, event):
                assert event.event == 'fizz'
                with self.lock:
                    self.received.append(('event', 'fizz', event.body))

            def buzz_event(self, event):
                assert event.event == 'buzz'
                with self.lock:
                    self.received.append(('event', 'buzz', event.body))

            def event(self, event):
                with self.lock:
                    self.received.append(('event', event.event, event.body))

            def make_and_log_response(self, request):
                x = random.randint(-100, 100)
                if x < 0:
                    exc_type = (
                        messaging.InvalidMessageError if x % 2
                        else messaging.MessageHandlingError
                    )
                    x = exc_type(str(x), request)
                with self.lock:
                    self.responses_sent.append((request.seq, x))
                return x

            def fizz_request(self, request):
                assert request.command == 'fizz'
                with self.lock:
                    self.received.append(('request', 'fizz', request.arguments))
                return self.make_and_log_response(request)

            def buzz_request(self, request):
                assert request.command == 'buzz'
                with self.lock:
                    self.received.append(('request', 'buzz', request.arguments))
                return self.make_and_log_response(request)

            def request(self, request):
                with self.lock:
                    self.received.append(('request', request.command, request.arguments))
                return self.make_and_log_response(request)

            def _got_response(self, response):
                with self.lock:
                    self.responses_received.append((response.request.seq, response.body))

            def _send_requests_and_events(self, channel):
                types = [random.choice(('event', 'request')) for _ in range(0, 100)]

                for typ in types:
                    name = random.choice(('fizz', 'buzz', 'fizzbuzz'))
                    body = random.randint(0, 100)

                    with self.lock:
                        self.sent.append((typ, name, body))

                    if typ == 'event':
                        channel.send_event(name, body)
                    elif typ == 'request':
                        req = channel.send_request(name, body)
                        req.on_response(self._got_response)

                channel.send_event("done")

                # Spin until we receive "done", and also get responses to all requests.
                requests_sent = types.count("request")
                print(fmt("{0} waiting for {1} responses ...", self.name, requests_sent))
                while True:
                    with self.lock:
                        if self.done:
                            if requests_sent == len(self.responses_received):
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

            stream1 = LoggingJsonStream(messaging.JsonIOStream(io1, io1))
            channel1 = messaging.JsonMessageChannel(stream1, fuzzer1)
            channel1.start()
            fuzzer1.start(channel1)

            stream2 = LoggingJsonStream(messaging.JsonIOStream(io2, io2))
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
