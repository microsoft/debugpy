# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

import collections
import itertools
import json
import sys
import threading


class JsonIOStream(object):
    """Implements a JSON value stream over two byte streams (input and output).

    Each value is encoded as a packet consisting of a header and a body, as defined by the
    Debug Adapter Protocol (https://microsoft.github.io/debug-adapter-protocol/overview).
    """

    MAX_BODY_SIZE = 0xFFFFFF

    @classmethod
    def from_stdio(cls):
        if sys.version_info >= (3,):
            stdin = sys.stdin.buffer
            stdout = sys.stdout.buffer
        else:
            stdin = sys.stdin
            stdout = sys.stdout
            if sys.platform == 'win32':
                import os, msvcrt
                msvcrt.setmode(stdin.fileno(), os.O_BINARY)
                msvcrt.setmode(stdout.fileno(), os.O_BINARY)
        return cls(stdin, stdout)

    @classmethod
    def from_socket(cls, socket):
        if socket.gettimeout() is not None:
            raise ValueError('Socket must be in blocking mode')
        socket_io = socket.makefile('rwb', 0)
        return cls(socket_io, socket_io)

    def __init__(self, reader, writer):
        """Creates a new JsonIOStream.

        reader is a BytesIO-like object from which incoming messages are read;
        reader.readline() must treat '\n' as the line terminator, and must leave
        '\r' as is (i.e. it must not translate '\r\n' to just plain '\n'!).

        writer is a BytesIO-like object to which outgoing messages are written.
        """
        self._reader = reader
        self._writer = writer
        self._is_closing = False

    def close(self):
        self._is_closing = True
        self._reader.close()
        self._writer.close()

    def _read_line(self):
        line = b''
        while True:
            line += self._reader.readline()
            if not line:
                raise EOFError
            if line.endswith(b'\r\n'):
                line = line[0:-2]
                return line

    def read_json(self):
        """Read a single JSON value from reader.

        Returns JSON value as parsed by json.loads(), or raises EOFError
        if there are no more objects to be read.
        """

        headers = {}
        while True:
            try:
                line = self._read_line()
            except Exception:
                if self._is_closing:
                    raise EOFError
                else:
                    raise

            if line == b'':
                break
            key, _, value = line.partition(b':')
            headers[key] = value

        try:
            length = int(headers[b'Content-Length'])
            if not (0 <= length <= self.MAX_BODY_SIZE):
                raise ValueError
        except (KeyError, ValueError):
            raise IOError('Content-Length is missing or invalid')

        try:
            body = self._reader.read(length)
        except Exception:
            if self._is_closing:
                raise EOFError
            else:
                raise

        if isinstance(body, bytes):
            body = body.decode('utf-8')
        return json.loads(body)

    def write_json(self, value):
        """Write a single JSON object to writer.

        object must be in the format suitable for json.dump().
        """

        body = json.dumps(value, sort_keys=True)
        if not isinstance(body, bytes):
            body = body.encode('utf-8')

        header = 'Content-Length: %d\r\n\r\n' % len(body)
        if not isinstance(header, bytes):
            header = header.encode('ascii')

        self._writer.write(header)
        self._writer.write(body)


Response = collections.namedtuple('Response', ('success', 'command', 'error_message', 'body'))
Response.__new__.__defaults__ = (None, None)
class Response(Response):
    """Represents a received response to a Request."""


class RequestFailure(Exception):
    def __init__(self, message):
        self.message = message


class Request(object):
    """Represents a request that was sent to the other party, and is awaiting or has
    already received a response.
    """

    def __init__(self, channel, seq):
        self.channel = channel
        self.seq = seq
        self.response = None
        self._lock = threading.Lock()
        self._got_response = threading.Event()
        self._callback = lambda _: None

    def _handle_response(self, success, command, error_message=None, body=None):
        assert self.response is None
        with self._lock:
            response = Response(success, command, error_message, body)
            self.response = response
            callback = self._callback
        callback(response)
        self._got_response.set()

    def wait_for_response(self, raise_if_failed=True):
        """Waits until a response is received for this request, records that
        response as a new Response object accessible via self.response,
        and returns self.response.body.

        If raise_if_failed is True, and the received response does not indicate
        success, raises RequestFailure. Otherwise, self.response.success has to
        be inspected to determine whether the request failed or succeeded, since
        self.response.body can be None in either case.
        """

        self._got_response.wait()
        if raise_if_failed and not self.response.success:
            raise RequestFailure(self.response.error_message)
        return self.response

    def on_response(self, callback):
        """Registers a callback to invoke when a response is received for this
        request. If response was already received, invokes callback immediately.
        Callback is invoked with Response object as the sole argument.

        The callback is invoked on an unspecified background thread that performs
        processing of incoming messages; therefore, no further message processing
        occurs until the callback returns.
        """

        with self._lock:
            response = self.response
            if response is None:
                self._callback = callback
                return
        callback(response)


class JsonMessageChannel(object):
    """Implements a JSON message channel on top of a JSON stream, with
    support for generic Request, Response and Event messages as defined by the
    Debug Adapter Protocol (https://microsoft.github.io/debug-adapter-protocol/overview).
    """

    def __init__(self, stream, handlers=None):
        self.stream = stream
        self.send_callback = lambda channel, message: None
        self.receive_callback = lambda channel, message: None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._seq_iter = itertools.count(1)
        self._requests = {}
        self._handlers = handlers
        self._worker = threading.Thread(target=self._process_incoming_messages)
        self._worker.daemon = True

    def close(self):
        self.stream.close()

    def start(self):
        self._worker.start()

    def wait(self):
        self._worker.join()

    def _send_message(self, type, rest={}):
        with self._lock:
            seq = next(self._seq_iter)
        message = {
            'seq': seq,
            'type': type,
        }
        message.update(rest)
        with self._lock:
            self.stream.write_json(message)
        self.send_callback(self, message)
        return seq

    def send_request(self, command, arguments=None):
        d = {'command': command}
        if arguments is not None:
            d['arguments'] = arguments
        seq = self._send_message('request', d)
        request = Request(self, seq)
        with self._lock:
            self._requests[seq] = request
        return request

    def send_event(self, event, body=None):
        d = {'event': event}
        if body is not None:
            d['body'] = body
        self._send_message('event', d)

    def send_response(self, request_seq, success, command, error_message=None, body=None):
        d = {
            'request_seq': request_seq,
            'success': success,
            'command': command,
        }
        if success:
            if body is not None:
                d['body'] = body
        else:
            if error_message is not None:
                d['message'] = error_message
        self._send_message('response', d)

    def on_message(self, message):
        self.receive_callback(self, message)
        seq = message['seq']
        typ = message['type']
        if typ == 'request':
            command = message['command']
            arguments = message.get('arguments', None)
            self.on_request(seq, command, arguments)
        elif typ == 'event':
            event = message['event']
            body = message.get('body', None)
            self.on_event(seq, event, body)
        elif typ == 'response':
            request_seq = message['request_seq']
            success = message['success']
            command = message['command']
            error_message = message.get('message', None)
            body = message.get('body', None)
            self.on_response(seq, request_seq, success, command, error_message, body)
        else:
            raise IOError('Incoming message has invalid "type":\n%r' % message)

    def on_request(self, seq, command, arguments):
        handler_name = '%s_request' % command
        specific_handler = getattr(self._handlers, handler_name, None)
        if specific_handler is not None:
            handler = lambda: specific_handler(self, arguments)
        else:
            generic_handler = getattr(self._handlers, 'request')
            handler = lambda: generic_handler(self, command, arguments)
        try:
            response_body = handler()
        except Exception as ex:
            self.send_response(seq, False, command, str(ex))
        else:
            self.send_response(seq, True, command, None, response_body)

    def on_event(self, seq, event, body):
        handler_name = '%s_event' % event
        specific_handler = getattr(self._handlers, handler_name, None)
        if specific_handler is not None:
            handler = lambda: specific_handler(self, body)
        else:
            generic_handler = getattr(self._handlers, 'event')
            handler = lambda: generic_handler(self, event, body)
        handler()

    def on_response(self, seq, request_seq, success, command, error_message, body):
        try:
            with self._lock:
                request = self._requests.pop(request_seq)
        except KeyError:
            raise KeyError('Received response to unknown request %d', request_seq)
        return request._handle_response(success, command, error_message, body)

    def _process_incoming_messages(self):
        while True:
            try:
                message = self.stream.read_json()
            except EOFError:
                break
            try:
                self.on_message(message)
            except Exception:
                print('Error while processing message:\n%r\n\n' % message, file=sys.__stderr__)
                raise


class MessageHandlers(object):
    """A simple delegating message handlers object for use with JsonMessageChannel.
    For every argument provided, the object has an attribute with the corresponding
    name and value. Example:
    """

    def __init__(self, **kwargs):
        for name, func in kwargs.items():
            setattr(self, name, func)