# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import contextlib
import inspect
import itertools
import json
import sys
import threading

from ptvsd.common import log
from ptvsd.common._util import new_hidden_thread


class JsonIOStream(object):
    """Implements a JSON value stream over two byte streams (input and output).

    Each value is encoded as a packet consisting of a header and a body, as defined by the
    Debug Adapter Protocol (https://microsoft.github.io/debug-adapter-protocol/overview).
    """

    MAX_BODY_SIZE = 0xFFFFFF

    @classmethod
    def from_stdio(cls, name='???'):
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
        return cls(stdin, stdout, name)

    @classmethod
    def from_socket(cls, socket, name='???'):
        if socket.gettimeout() is not None:
            raise ValueError('Socket must be in blocking mode')
        socket_io = socket.makefile('rwb', 0)
        return cls(socket_io, socket_io, name)

    def __init__(self, reader, writer, name='???'):
        """Creates a new JsonIOStream.

        reader is a BytesIO-like object from which incoming messages are read;
        reader.readline() must treat '\n' as the line terminator, and must leave
        '\r' as is (i.e. it must not translate '\r\n' to just plain '\n'!).

        writer is a BytesIO-like object to which outgoing messages are written.
        """
        self.name = name
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
            try:
                line += self._reader.readline()
            except Exception:
                raise EOFError
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

        # Parse the message, and try to log any failures using as much information
        # as we already have at the point of the failure. For example, if it fails
        # after decoding during JSON parsing, log as a Unicode string, rather than
        # a bytestring.

        headers = {}
        while True:
            line = self._read_line()
            if line == b'':
                break
            key, _, value = line.partition(b':')
            headers[key] = value

        try:
            length = int(headers[b'Content-Length'])
            if not (0 <= length <= self.MAX_BODY_SIZE):
                raise ValueError
        except (KeyError, ValueError):
            log.exception('{0} --> {1}', self.name, headers)
            raise IOError('Content-Length is missing or invalid')

        try:
            body = b''
            while length > 0:
                chunk = self._reader.read(length)
                body += chunk
                length -= len(chunk)
        except Exception:
            if self._is_closing:
                raise EOFError
            else:
                raise

        try:
            body = body.decode('utf-8')
        except Exception:
            log.exception('{0} --> {1}', self.name, body)
            raise

        try:
            body = json.loads(body)
        except Exception:
            log.exception('{0} --> {1}', self.name, body)
            raise

        log.debug('{0} --> {1!j}', self.name, body)
        return body


    def write_json(self, value):
        """Write a single JSON object to writer.

        object must be in the format suitable for json.dump().
        """

        try:
            body = json.dumps(value, sort_keys=True)
        except Exception:
            log.exception('{0} <-- {1!r}', self.name, value)

        if not isinstance(body, bytes):
            body = body.encode('utf-8')

        header = u'Content-Length: {0}\r\n\r\n'.format(len(body))
        header = header.encode('ascii')

        try:
            self._writer.write(header)
            self._writer.write(body)
        except Exception:
            log.exception('{0} <-- {1!j}', self.name, value)
            raise

        log.debug('{0} <-- {1!j}', self.name, value)


class Message(object):
    """Represents an incoming or an outgoing message.
    """

    def __init__(self, channel, seq):
        self.channel = channel
        self.seq = seq


class Request(Message):
    """Represents an incoming or an outgoing request.

    Incoming requests are represented by instances of this class.

    Outgoing requests are represented by instances of OutgoingRequest, which
    provides additional functionality to handle responses.
    """

    def __init__(self, channel, seq, command, arguments):
        super(Request, self).__init__(channel, seq)
        self.command = command
        self.arguments = arguments
        self.response = None


class OutgoingRequest(Request):
    """Represents an outgoing request, for which it is possible to wait for a
    response to be received, and register a response callback.
    """

    def __init__(self, channel, seq, command, arguments):
        super(OutgoingRequest, self).__init__(channel, seq, command, arguments)
        self._lock = threading.Lock()
        self._got_response = threading.Event()
        self._callback = lambda _: None

    def _handle_response(self, seq, command, body):
        assert self.response is None
        with self._lock:
            response = Response(self.channel, seq, self, body)
            self.response = response
            callback = self._callback
        callback(response)
        self._got_response.set()
        return response

    def wait_for_response(self, raise_if_failed=True):
        """Waits until a response is received for this request, records that
        response as a new Response object accessible via self.response, and
        returns self.response.body.

        If raise_if_failed is True, and the received response does not indicate
        success, raises RequestFailure. Otherwise, self.response.body has to be
        inspected to determine whether the request failed or succeeded.
        """

        self._got_response.wait()
        if raise_if_failed and not self.response.success:
            raise self.response.body
        return self.response.body

    def on_response(self, callback):
        """Registers a callback to invoke when a response is received for this
        request. If response was already received, invokes callback immediately.
        Callback is invoked with Response as the sole arugment.

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


class Response(Message):
    """Represents an incoming or an outgoing response to a Request.
    """

    def __init__(self, channel, seq, request, body):
        super(Response, self).__init__(channel, seq)

        self.request = request
        """Request object that this is a response to.
        """

        self.body = body
        """Body of the response if the request was successful, or an instance
        of some class derived from Exception it it was not.

        If a response was received from the other side, but it was marked as
        failure, it is an instance of RequestFailure, capturing the received
        error message.

        If a response was never received from the other side (e.g. because it
        disconnected before sending a response), it is EOFError.
        """

    @property
    def success(self):
        return not isinstance(self.body, Exception)

    @property
    def result(self):
        """Result of the request. Returns the value of response.body, unless it
        is an exception, in which case it is raised instead.
        """

        if self.success:
            return self.body
        else:
            raise self.body


class Event(Message):
    """Represents an incoming event.
    """

    def __init__(self, channel, seq, event, body):
        super(Event, self).__init__(channel, seq)
        self.event = event
        self.body = body


class RequestFailure(Exception):
    def __init__(self, message):
        self.message = message

    def __hash__(self):
        return hash(self.message)

    def __eq__(self, other):
        if not isinstance(other, RequestFailure):
            return NotImplemented
        return self.message == other.message

    def __ne__(self, other):
        return not self == other

    def __repr__(self):
        return 'RequestFailure(%r)' % self.message

    def __str__(self):
        return self.message


class JsonMessageChannel(object):
    """Implements a JSON message channel on top of a JSON stream, with
    support for generic Request, Response and Event messages as defined by the
    Debug Adapter Protocol (https://microsoft.github.io/debug-adapter-protocol/overview).
    """

    def __init__(self, stream, handlers=None, name=None):
        self.stream = stream
        self.name = name if name is not None else stream.name
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._seq_iter = itertools.count(1)
        self._requests = {}
        self._handlers = handlers
        self._worker = new_hidden_thread('{} message channel worker'.format(self.name), self._process_incoming_messages)
        self._worker.daemon = True

    def close(self):
        self.stream.close()

    def start(self):
        self._worker.start()

    def wait(self):
        self._worker.join()

    @contextlib.contextmanager
    def _send_message(self, type, rest={}):
        with self._lock:
            seq = next(self._seq_iter)
        message = {
            'seq': seq,
            'type': type,
        }
        message.update(rest)
        with self._lock:
            yield seq
            self.stream.write_json(message)

    def send_request(self, command, arguments=None):
        d = {'command': command}
        if arguments is not None and arguments != {}:
            d['arguments'] = arguments
        with self._send_message('request', d) as seq:
            request = OutgoingRequest(self, seq, command, arguments)
            self._requests[seq] = request
        return request

    def send_event(self, event, body=None):
        d = {'event': event}
        if body is not None and body != {}:
            d['body'] = body
        with self._send_message('event', d):
            pass

    def propagate(self, message):
        """Sends a new message with the same type and payload.

        If it was a request, returns the new OutgoingRequest object for it.
        """

        if isinstance(message, Request):
            return self.send_request(message.command, message.arguments)
        else:
            self.send_event(message.event, message.body)

    def delegate(self, request):
        """Propagates a request, waits for response, and returns its body.

        If the request failed, raises RequestFailure, just like wait_for_response().
        """
        assert isinstance(request, Request)
        return self.propagate(request).wait_for_response()

    def _send_response(self, request, body):
        d = {
            'request_seq': request.seq,
            'command': request.command,
        }
        if isinstance(body, Exception):
            d['success'] = False
            d['message'] = str(body)
        else:
            d['success'] = True
            if body is not None and body != {}:
                d['body'] = body

        with self._send_message('response', d) as seq:
            pass
        return Response(self, seq, request, body)

    def on_message(self, message):
        seq = message['seq']
        typ = message['type']
        if typ == 'request':
            command = message['command']
            arguments = message.get('arguments', None)
            return self.on_request(seq, command, arguments)
        elif typ == 'event':
            event = message['event']
            body = message.get('body', None)
            return self.on_event(seq, event, body)
        elif typ == 'response':
            request_seq = message['request_seq']
            success = message['success']
            command = message['command']
            error_message = message.get('message', None)
            body = message.get('body', None)
            return self.on_response(seq, request_seq, success, command, error_message, body)
        else:
            raise IOError('Incoming message has invalid "type":\n%r' % message)

    def on_request(self, seq, command, arguments):
        handler_name = '%s_request' % command
        handler = getattr(self._handlers, handler_name, None)
        if handler is None:
            try:
                handler = getattr(self._handlers, 'request')
            except AttributeError:
                raise AttributeError('%r has no handler for request %r' % (self._handlers, command))

        request = Request(self, seq, command, arguments)
        try:
            result = handler(request)
        except RequestFailure as ex:
            result = ex

        # A request handler can either be a simple function that returns the body of the
        # response directly, or a generator that yields. If it is a generator, then every
        # yield of None is treated as request to process another pending message recursively,
        # after which the generator is resumed. Once any object other than None is yielded,
        # that is the body of the response. If the generator stops before yielding a body,
        # it is treated as if it had yielded {}.
        if inspect.isgenerator(result):
            gen = result
        else:
            # Wrap a non-generator return into a generator, to unify processing below.
            # Note that return None is the same as return {} in this case, unlike yield.
            def gen():
                yield {} if result is None else result
            gen = gen()

        last_message = None
        while True:
            try:
                response_body = gen.send(last_message)
            except RequestFailure as ex:
                response_body = ex
                break
            except StopIteration:
                response_body = {}

            if response_body is not None:
                gen.close()
                break
            last_message = self._process_incoming_message()  # re-entrant

        request.response = self._send_response(request, response_body)
        return request

    def on_event(self, seq, event, body):
        handler_name = '%s_event' % event
        handler = getattr(self._handlers, handler_name, None)
        if handler is None:
            try:
                handler = getattr(self._handlers, 'event')
            except AttributeError:
                raise AttributeError('%r has no handler for event %r' % (self._handlers, event))

        event = Event(self, seq, event, body)
        handler(event)
        return event

    def on_response(self, seq, request_seq, success, command, error_message, body):
        try:
            with self._lock:
                request = self._requests.pop(request_seq)
        except KeyError:
            raise KeyError('Received response to unknown request %d', request_seq)
        if not success:
            body = RequestFailure(error_message)
        return request._handle_response(seq, command, body)

    def on_disconnect(self):
        # There's no more incoming messages, so any requests that are still pending
        # must be marked as failed to unblock anyone waiting on them.
        with self._lock:
            for request in self._requests.values():
                request._handle_response(None, request.command, EOFError('No response'))
        getattr(self._handlers, 'disconnect', lambda: None)()

    def _process_incoming_message(self):
        message = self.stream.read_json()
        try:
            return self.on_message(message)
        except Exception:
            log.exception('Error while processing message for {0}:\n\n{1!r}', self.name, message)
            raise

    def _process_incoming_messages(self):
        try:
            while True:
                try:
                    self._process_incoming_message()
                except EOFError:
                    return False
        finally:
            try:
                self.on_disconnect()
            except Exception:
                log.exception('Error while processing disconnect for {0}', self.name)
                raise


class MessageHandlers(object):
    """A simple delegating message handlers object for use with JsonMessageChannel.
    For every argument provided, the object has an attribute with the corresponding
    name and value.
    """

    def __init__(self, **kwargs):
        for name, func in kwargs.items():
            setattr(self, name, func)


def raise_failure(fmt, *args, **kwargs):
    """Raises RequestFailure from the point at which it is invoked with the specified
    formatted message. The message is also immediately logged.
    """

    msg = log.formatter.format(fmt, *args, **kwargs)
    try:
        raise RequestFailure(msg)
    except RequestFailure:
        log.exception()
        raise
