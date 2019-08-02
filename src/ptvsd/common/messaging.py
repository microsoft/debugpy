# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

"""An implementation of the session and presentation layers as used in the Debug
Adapter Protocol (DAP): channels and their lifetime, JSON messages, requests,
responses, and events.

https://microsoft.github.io/debug-adapter-protocol/overview#base-protocol
"""

import collections
import contextlib
import functools
import inspect
import itertools
import sys
import threading

from ptvsd.common import compat, fmt, json, log, util


class JsonIOStream(object):
    """Implements a JSON value stream over two byte streams (input and output).

    Each value is encoded as a DAP packet, with metadata headers and a JSON payload.
    """

    MAX_BODY_SIZE = 0xFFFFFF

    json_decoder_factory = json.JsonDecoder
    """Used by read_json() when decoder is None."""

    json_encoder_factory = json.JsonEncoder
    """Used by write_json() when encoder is None."""

    @classmethod
    def from_stdio(cls, name="stdio"):
        """Creates a new instance that receives messages from sys.stdin, and sends
        them to sys.stdout.

        On Win32, this also sets stdin and stdout to binary mode, since the protocol
        requires that to work properly.
        """
        if sys.version_info >= (3,):
            stdin = sys.stdin.buffer
            stdout = sys.stdout.buffer
        else:
            stdin = sys.stdin
            stdout = sys.stdout
            if sys.platform == "win32":
                import os, msvcrt

                msvcrt.setmode(stdin.fileno(), os.O_BINARY)
                msvcrt.setmode(stdout.fileno(), os.O_BINARY)
        return cls(stdin, stdout, name)

    @classmethod
    def from_socket(cls, socket, name=None):
        """Creates a new instance that sends and receives messages over a socket.
        """
        socket.settimeout(None)  # make socket blocking
        if name is None:
            name = repr(socket)

        # TODO: investigate switching to buffered sockets; readline() on unbuffered
        # sockets is very slow! Although the implementation of readline() itself is
        # native code, it calls read(1) in a loop - and that then ultimately calls
        # SocketIO.readinto(), which is implemented in Python.
        socket_io = socket.makefile("rwb", 0)

        return cls(socket_io, socket_io, name)

    def __init__(self, reader, writer, name=None):
        """Creates a new JsonIOStream.

        reader must be a BytesIO-like object, from which incoming messages will be
        read by read_json().

        writer must be a BytesIO-like object, into which outgoing messages will be
        written by write_json().

        reader.readline() must treat "\n" as the line terminator, and must leave "\r"
        as is - it must not replace "\r\n" with "\n" automatically, as TextIO does.
        """

        if name is None:
            name = fmt("reader={0!r}, writer={1!r}", reader, writer)

        self.name = name
        self._reader = reader
        self._writer = writer
        self._is_closing = False

    def close(self):
        """Closes the stream, the reader, and the writer.
        """
        self._is_closing = True

        # Close the writer first, so that the other end of the connection has its
        # message loop waiting on read() unblocked. If there is an exception while
        # closing the writer, we still want to try to close the reader - only one
        # exception can bubble up, so if both fail, it'll be the one from reader.
        try:
            self._writer.close()
        finally:
            if self._reader is not self._writer:
                self._reader.close()

    def _log_message(self, dir, data, logger=log.debug):
        format_string = "{0} {1} " + (
            "{2!j:indent=None}" if isinstance(data, list) else "{2!j}"
        )
        return logger(format_string, self.name, dir, data)

    @staticmethod
    def _read_line(reader):
        line = b""
        while True:
            try:
                line += reader.readline()
            except Exception as ex:
                raise EOFError(str(ex))
            if not line:
                raise EOFError("No more data")
            if line.endswith(b"\r\n"):
                line = line[0:-2]
                return line

    def read_json(self, decoder=None):
        """Read a single JSON value from reader.

        Returns JSON value as parsed by decoder.decode(), or raises EOFError if
        there are no more values to be read.
        """

        decoder = decoder if decoder is not None else self.json_decoder_factory()
        reader = self._reader
        read_line = functools.partial(self._read_line, reader)

        # If any error occurs while reading and parsing the message, log the original
        # raw message data as is, so that it's possible to diagnose missing or invalid
        # headers, encoding issues, JSON syntax errors etc.
        def log_message_and_exception(format_string="", *args, **kwargs):
            if format_string:
                format_string += "\n\n"
            format_string += "{name} -->\n{raw_lines}"

            raw_lines = b"".join(raw_chunks).split(b"\n")
            raw_lines = "\n".join(repr(line) for line in raw_lines)

            return log.exception(
                format_string, *args, name=self.name, raw_lines=raw_lines, **kwargs
            )

        raw_chunks = []
        headers = {}

        while True:
            try:
                line = read_line()
            except Exception:
                # Only log it if we have already read some headers, and are looking
                # for a blank line terminating them. If this is the very first read,
                # there's no message data to log in any case, and the caller might
                # be anticipating the error - e.g. EOFError on disconnect.
                if headers:
                    raise log_message_and_exception(
                        "Error while reading message headers:"
                    )
                else:
                    raise

            raw_chunks += [line, b"\n"]
            if line == b"":
                break

            key, _, value = line.partition(b":")
            headers[key] = value

        try:
            length = int(headers[b"Content-Length"])
            if not (0 <= length <= self.MAX_BODY_SIZE):
                raise ValueError
        except (KeyError, ValueError):
            try:
                raise IOError("Content-Length is missing or invalid:")
            except Exception:
                raise log_message_and_exception()

        body_start = len(raw_chunks)
        body_remaining = length
        while body_remaining > 0:
            try:
                chunk = reader.read(body_remaining)
                if not chunk:
                    raise EOFError("No more data")
            except Exception:
                if self._is_closing:
                    raise EOFError
                else:
                    raise log_message_and_exception(
                        "Couldn't read the expected {0} bytes of body:", length
                    )

            raw_chunks.append(chunk)
            body_remaining -= len(chunk)
        assert body_remaining == 0

        body = b"".join(raw_chunks[body_start:])
        try:
            body = body.decode("utf-8")
        except Exception:
            raise log_message_and_exception()

        try:
            body = decoder.decode(body)
        except Exception:
            raise log_message_and_exception()

        # If parsed successfully, log as JSON for readability.
        self._log_message("-->", body)
        return body

    def write_json(self, value, encoder=None):
        """Write a single JSON value into writer.

        Value is written as encoded by encoder.encode().
        """

        encoder = encoder if encoder is not None else self.json_encoder_factory()
        writer = self._writer

        # Format the value as a message, and try to log any failures using as much
        # information as we already have at the point of the failure. For example,
        # if it fails after it is serialized to JSON, log that JSON.

        try:
            body = encoder.encode(value)
        except Exception:
            raise self._log_message("<--", value, logger=log.exception)
        if not isinstance(body, bytes):
            body = body.encode("utf-8")

        header = fmt("Content-Length: {0}\r\n\r\n", len(body))
        header = header.encode("ascii")

        data = header + body
        data_written = 0
        try:
            while data_written < len(data):
                written = writer.write(data[data_written:])
                # On Python 2, socket.makefile().write() does not properly implement
                # BytesIO.write(), and always returns None instead of the number of
                # bytes written - but also guarantees that it is always a full write.
                if written is None:
                    break
                data_written += written
            writer.flush()
        except Exception:
            raise self._log_message("<--", value, logger=log.exception)

        self._log_message("<--", value)

    def __repr__(self):
        return fmt("{0}({1!r})", type(self).__name__, self.name)


class MessageDict(collections.OrderedDict):
    """A specialized dict that is used for JSON message payloads - Request.arguments,
    Response.body, and Event.body.

    For all members that normally throw KeyError when a requested key is missing, this
    dict raises InvalidMessageError instead. Thus, a message handler can skip checks
    for missing properties, and just work directly with the payload on the assumption
    that it is valid according to the protocol specification; if anything is missing,
    it will be reported automatically in the proper manner.

    If the value for the requested key is itself a dict, it is returned as is, and not
    automatically converted to MessageDict. Thus, to enable convenient chaining - e.g.
    d["a"]["b"]["c"] - the dict must consistently use MessageDict instances rather than
    vanilla dicts for all its values, recursively. This is guaranteed for the payload
    of all freshly received messages (unless and until it is mutated), but there is no
    such guarantee for outgoing messages.
    """

    def __init__(self, message, items=None):
        assert message is None or isinstance(message, Message)

        if items is None:
            super(MessageDict, self).__init__()
        else:
            super(MessageDict, self).__init__(items)

        self.message = message
        """The Message object that owns this dict. If None, then MessageDict behaves
        like a regular dict - i.e. raises KeyError.

        For any instance exposed via a Message object corresponding to some incoming
        message, it is guaranteed to reference that Message object. There is no similar
        guarantee for outgoing messages.
        """

    def __repr__(self):
        return dict.__repr__(self)

    def __call__(self, key, validate, optional=False):
        """Like get(), but with validation.

        The item is first retrieved as if with self.get(key, default=()) - the default
        value is () rather than None, so that JSON nulls are distinguishable from
        missing properties.

        If optional=True, and the value is (), it's returned as is. Otherwise, the
        item is validated by invoking validate(item) on it.

        If validate=False, it's treated as if it were (lambda x: x) - i.e. any value
        is considered valid, and is returned unchanged. If validate is a type or a
        tuple, it's treated as if it were json.of_type(validate).

        If validate() returns successfully, the item is substituted with the value
        it returns - thus, the validator can e.g. replace () with a suitable default
        value for the property.

        If validate() raises TypeError or ValueError, and self.message is not None,
        __call__ raises InvalidMessageError that applies_to(self.message) with the
        same text. If self.message is None, the exception is propagated as is.

        See ptvsd.common.json for reusable validators.
        """

        if not validate:
            validate = lambda x: x
        elif isinstance(validate, type) or isinstance(validate, tuple):
            validate = json.of_type(validate)

        value = self.get(key, ())
        try:
            value = validate(value)
        except (TypeError, ValueError) as exc:
            if self.message is None:
                raise
            else:
                self.message.isnt_valid("{0!r} {1}", key, exc)
        return value

    def _invalid_if_no_key(func):
        def wrap(self, key, *args, **kwargs):
            try:
                return func(self, key, *args, **kwargs)
            except KeyError:
                if self.message is None:
                    raise
                else:
                    self.message.isnt_valid("missing property {0!r}", key)

        return wrap

    __getitem__ = _invalid_if_no_key(collections.OrderedDict.__getitem__)
    __delitem__ = _invalid_if_no_key(collections.OrderedDict.__delitem__)
    pop = _invalid_if_no_key(collections.OrderedDict.pop)

    del _invalid_if_no_key


class Message(object):
    """Represents a fully parsed incoming or outgoing message.
    """

    def __init__(self, channel, seq):
        self.channel = channel

        self.seq = seq
        """Sequence number of the message in its channel.

        This can be None for synthesized Responses.
        """

    @property
    def payload(self):
        """Payload of the message - self.body or self.arguments, depending on the
        message type.
        """
        raise NotImplementedError

    def __call__(self, *args, **kwargs):
        """Same as self.payload(...)."""
        return self.payload(*args, **kwargs)

    def __contains__(self, key):
        """Same as (key in self.payload)."""
        return key in self.payload

    def is_event(self, event=None):
        if not isinstance(self, Event):
            return False
        return event is None or self.event == event

    def is_request(self, command=None):
        if not isinstance(self, Request):
            return False
        return command is None or self.command == command

    def is_response(self, command=None):
        if not isinstance(self, Response):
            return False
        return command is None or self.request.command == command

    @staticmethod
    def raise_error(*args, **kwargs):
        """raise_error([self], exc_type, format_string, *args, **kwargs)

        Raises a new exception of the specified type from the point at which it is
        invoked, with the specified formatted message as the reason.

        This method can be used either as a static method, or as an instance method.
        If invoked as an instance method, the resulting exception will have its cause
        set to the Message object on which raise_error() was called.
        """

        if isinstance(args[0], Message):
            cause, exc_type, format_string = args[0:3]
            args = args[3:]
        else:
            cause = None
            exc_type, format_string = args[0:2]
            args = args[2:]

        assert issubclass(exc_type, MessageHandlingError)
        reason = fmt(format_string, *args, **kwargs)
        raise exc_type(reason, cause)  # will log it

    def isnt_valid(*args, **kwargs):
        """isnt_valid([self], format_string, *args, **kwargs)

        Same as raise_error(InvalidMessageError, ...).
        """
        if isinstance(args[0], Message):
            args[0].raise_error(InvalidMessageError, *args[1:], **kwargs)
        else:
            Message.raise_error(InvalidMessageError, *args, **kwargs)

    def cant_handle(*args, **kwargs):
        """cant_handle([self], format_string, *args, **kwargs)

        Same as raise_error(MessageHandlingError, ...).
        """
        if isinstance(args[0], Message):
            args[0].raise_error(MessageHandlingError, *args[1:], **kwargs)
        else:
            Message.raise_error(MessageHandlingError, *args, **kwargs)


class Request(Message):
    """Represents an incoming or an outgoing request.

    Incoming requests are represented directly by instances of this class.

    Outgoing requests are represented by instances of OutgoingRequest, which
    provides additional functionality to handle responses.
    """

    def __init__(self, channel, seq, command, arguments):
        super(Request, self).__init__(channel, seq)

        self.command = command

        self.arguments = arguments
        """Request arguments.

        For incoming requests, it is guaranteed that this is a MessageDict, and that
        any nested dicts are also MessageDict instances. If "arguments" was missing
        or null in JSON, arguments is an empty MessageDict - it is never None.
        """

        self.response = None
        """Set to Response object for the corresponding response, once the request
        is handled.

        For incoming requests, it is set as soon as the request handler returns.

        For outgoing requests, it is set as soon as the response is received, and
        before Response.on_request is invoked.
        """

    @property
    def payload(self):
        return self.arguments


class OutgoingRequest(Request):
    """Represents an outgoing request, for which it is possible to wait for a
    response to be received, and register a response callback.
    """

    def __init__(self, channel, seq, command, arguments):
        super(OutgoingRequest, self).__init__(channel, seq, command, arguments)
        self._got_response = threading.Event()
        self._callback = lambda _: None

    def _handle_response(self, response):
        assert self is response.request
        assert self.response is None
        assert self.channel is response.channel

        with self.channel:
            self.response = response
            callback = self._callback

        callback(response)
        self._got_response.set()

    def wait_for_response(self, raise_if_failed=True):
        """Waits until a response is received for this request, records the Response
        object for it in self.response, and returns response.body.

        If no response was received from the other party before the channel closed,
        self.response is a synthesized Response, which has EOFError() as its body.

        If raise_if_failed=True and response.success is False, raises response.body
        instead of returning.
        """
        self._got_response.wait()
        if raise_if_failed and not self.response.success:
            raise self.response.body
        return self.response.body

    def on_response(self, callback):
        """Registers a callback to invoke when a response is received for this request.
        The callback is invoked with Response as its sole argument.

        If response has already been received, invokes the callback immediately.

        It is guaranteed that self.response is set before the callback is invoked.

        If no response was received from the other party before the channel closed,
        a Response with body=EOFError() is synthesized.

        The callback may be invoked on an unspecified background thread that performs
        processing of incoming messages; in that case, no further message processing
        on the same channel will be performed until the callback returns.
        """

        # Locking the channel ensures that there's no race condition with disconnect
        # calling no_response(). Either we already have the synthesized response from
        # there, in which case we will invoke it below; or we don't, in which case
        # no_response() is yet to be called, and will invoke the callback.
        with self.channel:
            response = self.response
            if response is None:
                self._callback = callback
                return

        callback(response)

    def no_response(self):
        """Indicates that this request is never going to receive a proper response.

        Synthesizes the appopriate dummy Response, and invokes the callback with it.
        """
        response = Response(self.channel, None, self, EOFError("No response"))
        self._handle_response(response)


class Response(Message):
    """Represents an incoming or an outgoing response to a Request.
    """

    def __init__(self, channel, seq, request, body):
        super(Response, self).__init__(channel, seq)

        self.request = request

        self.body = body
        """Body of the response if the request was successful, or an instance
        of some class derived from Exception it it was not.

        If a response was received from the other side, but request failed, it is an
        instance of MessageHandlingError containing the received error message. If the
        error message starts with InvalidMessageError.PREFIX, then it's an instance of
        the InvalidMessageError specifically, and that prefix is stripped.

        If no response was received from the other party before the channel closed,
        it is an instance of EOFError.
        """

    @property
    def payload(self):
        return self.body

    @property
    def success(self):
        """Whether the request succeeded or not.
        """
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

    @property
    def payload(self):
        return self.body


class MessageHandlingError(Exception):
    """Indicates that a message couldn't be handled for some reason.

    If the reason is a contract violation - i.e. the message that was handled did not
    conform to the protocol specification - InvalidMessageError, which is a subclass,
    should be used instead.

    If any message handler raises an exception not derived from this class, it will
    escape the message loop unhandled, and terminate the process.

    If any message handler raises this exception, but applies_to(message) is False, it
    is treated as if it was a generic exception, as desribed above. Thus, if a request
    handler issues another request of its own, and that one fails, the failure is not
    silently propagated. However, a request that is delegated via Request.delegate()
    will also propagate failures back automatically. For manual propagation, catch the
    exception, and call exc.propagate().

    If any event handler raises this exception, and applies_to(event) is True, the
    exception is silently swallowed by the message loop.

    If any request handler raises this exception, and applies_to(request) is True, the
    exception is silently swallowed by the message loop, and a failure response is sent
    with "message" set to str(reason).

    Note that, while errors are not logged when they're swallowed by the message loop,
    by that time they have already been logged by their __init__ (when instantiated).
    """

    def __init__(self, reason, cause=None):
        """Creates a new instance of this class, and immediately logs the exception.

        Message handling errors are logged immediately, so that the precise context
        in which they occured can be determined from the surrounding log entries.
        """

        self.reason = reason
        """Why it couldn't be handled. This can be any object, but usually it's either
        str or Exception.
        """

        assert cause is None or isinstance(cause, Message)
        self.cause = cause
        """The Message object for the message that couldn't be handled. For responses
        to unknown requests, this is a synthetic Request.
        """

        try:
            raise self
        except MessageHandlingError:
            # TODO: change to E after unifying logging with tests
            log.exception(level="info")

    def __hash__(self):
        return hash((self.reason, id(self.cause)))

    def __eq__(self, other):
        if not isinstance(other, MessageHandlingError):
            return NotImplemented
        if type(self) is not type(other):
            return NotImplemented
        if self.reason != other.reason:
            return False
        if self.cause is not None and other.cause is not None:
            if self.cause.seq != other.cause.seq:
                return False
        return True

    def __ne__(self, other):
        return not self == other

    def __str__(self):
        return str(self.reason)

    def __repr__(self):
        s = type(self).__name__
        if self.cause is None:
            s += fmt("(reason={0!r})", self.reason)
        else:
            s += fmt(
                "(channel={0!r}, cause={1!r}, reason={2!r})",
                self.cause.channel.name,
                self.cause.seq,
                self.reason,
            )
        return s

    def applies_to(self, message):
        """Whether this MessageHandlingError can be treated as a reason why the
        handling of message failed.

        If self.cause is None, this is always true.

        If self.cause is not None, this is only true if cause is message.
        """
        return self.cause is None or self.cause is message

    def propagate(self, new_cause):
        """Propagates this error, raising a new instance of the same class with the
        same reason, but a different cause.
        """
        raise type(self)(self.reason, new_cause)


class InvalidMessageError(MessageHandlingError):
    """Indicates that an incoming message did not follow the protocol specification -
    for example, it was missing properties that are required, or the message itself
    is not allowed in the current state.

    Raised by MessageDict in lieu of KeyError for missing keys.
    """

    PREFIX = "Invalid message: "
    """Automatically prepended to the "message" property in JSON responses, when the
    handler raises InvalidMessageError.

    If a failed response has "message" property that starts with this prefix, it is
    reported as InvalidMessageError rather than MessageHandlingError.
    """

    def __str__(self):
        return InvalidMessageError.PREFIX + str(self.reason)


class JsonMessageChannel(object):
    """Implements a JSON message channel on top of a raw JSON message stream, with
    support for DAP requests, responses, and events.

    The channel can be locked for exclusive use via the with-statement::

        with channel:
            channel.send_request(...)
            # No interleaving messages can be sent here from other threads.
            channel.send_event(...)
    """

    report_unhandled_events = True
    """If True, any event that couldn't be handled successfully will be reported
    by sending a corresponding "event_not_handled" event in response. Can be set
    per-instance.

    This helps diagnose why important events are seemingly ignored, when the only
    message log that is available is the one for the other end of the channel.
    """

    def __init__(self, stream, handlers=None, name=None):
        self.stream = stream
        self.handlers = handlers
        self.name = name if name is not None else stream.name
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._seq_iter = itertools.count(1)
        self._requests = {}
        self._worker = util.new_hidden_thread(repr(self), self._process_incoming_messages)
        self._worker.daemon = True

    def __repr__(self):
        return fmt("{0}({1!r})", type(self).__name__, self.name)

    def __enter__(self):
        self._lock.acquire()
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        self._lock.release()

    def close(self):
        """Closes the underlying stream.

        This does not immediately terminate any handlers that were already running,
        but they will be unable to respond.
        """
        self.stream.close()

    def start(self):
        """Starts a message loop on a background thread, which invokes on_message
        for every new incoming message, until the channel is closed.

        Incoming messages will not be processed at all until this is invoked.
        """
        self._worker.start()

    def wait(self):
        """Waits until the message loop terminates.
        """
        self._worker.join()

    @staticmethod
    def _prettify(message_dict):
        """Reorders items in a MessageDict such that it is more readable.
        """
        # https://microsoft.github.io/debug-adapter-protocol/specification
        keys = (
            "seq",
            "type",
            "request_seq",
            "success",
            "command",
            "event",
            "message",
            "arguments",
            "body",
            "error",
        )
        for key in keys:
            try:
                value = message_dict[key]
            except KeyError:
                continue
            del message_dict[key]
            message_dict[key] = value

    @contextlib.contextmanager
    def _send_message(self, message):
        """Sends a new message to the other party.

        Generates a new sequence number for the message, and provides it to the
        caller before the message is sent, using the context manager protocol::

            with send_message(...) as seq:
                # The message hasn't been sent yet.
                ...
            # Now the message has been sent.

        Safe to call concurrently for the same channel from different threads.
        """

        assert "seq" not in message
        with self:
            seq = next(self._seq_iter)

        message = MessageDict(None, message)
        message["seq"] = seq
        self._prettify(message)

        with self:
            yield seq
            self.stream.write_json(message)

    def send_request(self, command, arguments=None, on_before_send=None):
        """Sends a new request, and returns the OutgoingRequest object for it.

        If arguments is None or {}, "arguments" will be omitted in JSON.

        If on_before_send is not None, invokes on_before_send() with the request
        object as the sole argument, before the request actually gets sent.

        Does not wait for response - use OutgoingRequest.wait_for_response().

        Safe to call concurrently for the same channel from different threads.
        """

        d = {"type": "request", "command": command}
        if arguments is not None and arguments != {}:
            d["arguments"] = arguments

        with self._send_message(d) as seq:
            request = OutgoingRequest(self, seq, command, arguments)
            if on_before_send is not None:
                on_before_send(request)
            self._requests[seq] = request
        return request

    def send_event(self, event, body=None):
        """Sends a new event.

        If body is None or {}, "body" will be omitted in JSON.

        Safe to call concurrently for the same channel from different threads.
        """

        d = {"type": "event", "event": event}
        if body is not None and body != {}:
            d["body"] = body

        with self._send_message(d):
            pass

    def request(self, *args, **kwargs):
        """Same as send_request(...).wait_for_response()
        """
        return self.send_request(*args, **kwargs).wait_for_response()

    def propagate(self, message):
        """Sends a new message with the same type and payload.

        If it was a request, returns the new OutgoingRequest object for it.
        """
        if isinstance(message, Request):
            return self.send_request(message.command, message.arguments)
        else:
            self.send_event(message.event, message.body)

    def delegate(self, request):
        """Like propagate(request).wait_for_response(), but will also propagate
        any resulting MessageHandlingError back.
        """
        assert isinstance(request, Request)
        try:
            return self.propagate(request).wait_for_response()
        except MessageHandlingError as exc:
            exc.propagate(request)

    def _send_response(self, request, body):
        d = {"type": "response", "request_seq": request.seq, "command": request.command}

        if isinstance(body, Exception):
            d["success"] = False
            d["message"] = str(body)
        else:
            d["success"] = True
            if body != {}:
                d["body"] = body

        with self._send_message(d) as seq:
            pass

        response = Response(self, seq, request.seq, body)
        response.request = request
        return response

    @staticmethod
    def _get_payload(message, name):
        """Retrieves payload from a deserialized message.

        Same as message[name], but if that value is missing or null, it is treated
        as if it were {}.
        """

        payload = message.get(name, None)
        if payload is not None:
            if isinstance(payload, dict):  # can be int, str, list...
                assert isinstance(payload, MessageDict)
            return payload

        # Missing payload. Construct a dummy MessageDict, and make it look like
        # it was deserialized. See _process_incoming_message for why it needs to
        # have associate_with().

        def associate_with(message):
            payload.message = message

        payload = MessageDict(None)
        payload.associate_with = associate_with
        return payload

    def _on_message(self, message):
        """Invoked for every incoming message after deserialization, but before any
        further processing.

        The default implementation invokes _on_request, _on_response or _on_event,
        according to the type of the message.
        """

        seq = message["seq"]
        typ = message["type"]
        if typ == "request":
            command = message["command"]
            arguments = self._get_payload(message, "arguments")
            return self._on_request(seq, command, arguments)
        elif typ == "event":
            event = message["event"]
            body = self._get_payload(message, "body")
            return self._on_event(seq, event, body)
        elif typ == "response":
            request_seq = message["request_seq"]
            success = message["success"]
            command = message["command"]
            error_message = message.get("message", None)
            body = self._get_payload(message, "body") if success else None
            return self._on_response(
                seq, request_seq, success, command, error_message, body
            )
        else:
            message.isnt_valid('invalid "type": {0!r}', message.type)

    def _get_handler_for(self, type, name):
        for handler_name in (name + "_" + type, type):
            try:
                return getattr(self.handlers, handler_name)
            except AttributeError:
                continue
        raise AttributeError(
            fmt(
                "{0} has no {1} handler for {2!r}",
                compat.srcnameof(self.handlers),
                type,
                name,
            )
        )

    def _on_request(self, seq, command, arguments):
        """Invoked for every incoming request after deserialization and parsing, but
        before handling.

        It is guaranteed that arguments is a MessageDict, and all nested dicts in it are
        also MessageDict instances. If "arguments" was missing or null in JSON, this
        method receives an empty MessageDict. All dicts have owner=None, but it can be
        changed with arguments.associate_with().

        The default implementation tries to find a handler for command in self.handlers,
        and invoke it. Given command=X, if handlers.X_request exists, then it is the
        specific handler for this request. Otherwise, handlers.request must exist, and
        it is the generic handler for this request. A missing handler is a fatal error.

        The handler is then invoked with the Request object as its sole argument. It can
        either be a simple function that returns a value directly, or a generator that
        yields.

        If the handler returns a value directly, the response is sent immediately, with
        Response.body as the returned value. If the value is None, it is a fatal error.
        No further incoming messages are processed until the handler returns.

        If the handler returns a generator object, it will be iterated until it yields
        a non-None value. Every yield of None is treated as request to process another
        pending message recursively (which may cause re-entrancy in the handler), after
        which the generator is resumed with the Message object for that message.

        Once a non-None value is yielded from the generator, it is treated the same as
        in non-generator case. It is a fatal error for the generator to not yield such
        a value before it stops.

        Thus, when a request handler needs to wait until another request or event is
        handled before it can respond, it should yield in a loop, so that any other
        messages can be processed until that happens::

            while True:
                msg = yield
                if msg.is_event('party'):
                    break

        or when it's waiting for some change in state:

            self.ready = False
            while not self.ready:
                yield  # some other handler must set self.ready = True

        To fail the request, the handler must raise an instance of MessageHandlingError
        that applies_to() the Request object it was handling. Use Message.isnt_valid
        to report invalid requests, and Message.cant_handle to report valid requests
        that could not be processed.
        """

        handler = self._get_handler_for("request", command)
        request = Request(self, seq, command, arguments)

        if isinstance(arguments, dict):
            arguments.associate_with(request)

        def _assert_response(result):
            assert result is not None, fmt(
                "Request handler {0} must provide a response for {1!r}.",
                compat.srcnameof(handler),
                command,
            )

        try:
            result = handler(request)
        except MessageHandlingError as exc:
            if not exc.applies_to(request):
                raise
            result = exc
        _assert_response(result)

        if inspect.isgenerator(result):
            gen = result
        else:
            # Wrap a non-generator return into a generator, to unify processing below.
            def gen():
                yield result

            gen = gen()

        # Process messages recursively until generator yields the response.
        last_message = None
        while True:
            try:
                response_body = gen.send(last_message)
            except MessageHandlingError as exc:
                if not exc.applies_to(request):
                    raise
                response_body = exc
                break
            except StopIteration:
                response_body = {}

            if response_body is not None:
                gen.close()
                break

            last_message = self._process_incoming_message()  # re-entrant

        _assert_response(response_body)
        request.response = self._send_response(request, response_body)
        return request

    def _on_event(self, seq, event, body):
        """Invoked for every incoming event after deserialization and parsing, but
        before handling.

        It is guaranteed that body is a MessageDict, and all nested dicts in it are
        also MessageDict instances. If "body" was missing or null in JSON, this method
        receives an empty MessageDict. All dicts have owner=None, but it can be changed
        with body.associate_with().

        The default implementation tries to find a handler for event in self.handlers,
        and invoke it. Given event=X, if handlers.X_event exists, then it is the
        specific handler for this event. Otherwise, handlers.event must exist, and
        it is the generic handler for this event. A missing handler is a fatal error.

        No further incoming messages are processed until the handler returns.

        To report failure to handle the event, the handler must raise an instance of
        MessageHandlingError that applies_to() the Event object it was handling. Use
        Message.isnt_valid to report invalid events, and Message.cant_handle to report
        valid events that could not be processed.

        If report_unhandled_events is True, then failure to handle the event will be
        reported to the sender as an "event_not_handled" event. Otherwise, the sender
        does not receive any notifications.
        """

        handler = self._get_handler_for("event", event)
        event = Event(self, seq, event, body)

        if isinstance(body, dict):
            body.associate_with(event)

        try:
            result = handler(event)
        except MessageHandlingError as exc:
            if not exc.applies_to(event):
                raise
            if self.report_unhandled_events:
                message = exc.reason
                if isinstance(exc, InvalidMessageError):
                    message = InvalidMessageError.PREFIX + message
                self.send_event(
                    "event_not_handled", {"event_seq": seq, "message": message}
                )

        assert result is None, fmt(
            "Event handler {0} tried to respond to {1!r}.",
            compat.srcnameof(handler),
            event.event,
        )

        return event

    def _on_response(self, seq, request_seq, success, command, error_message, body):
        """Invoked for every incoming response after deserialization and parsing, but
        before handling.

        error_message corresponds to "message" in JSON, and is renamed for clarity.

        If success is False, body is None. Otherwise, it is guaranteed that body is
        a MessageDict, and all nested dicts in it are also MessageDict instances. If
        "body" was missing or null in JSON, this method receives an empty MessageDict.
        All dicts have owner=None, but it can be changed with body.associate_with().

        The default implementation delegates to the OutgoingRequest object for the
        request to which this is the response for further handling. If there is no
        such object - i.e. it is an unknown request - the response logged and ignored.

        See OutgoingRequest.on_response and OutgoingRequest.wait_for_response for
        high-level response handling facilities.

        No further incoming messages are processed until the handler returns.
        """

        # Synthetic Request that only has seq and command as specified in response JSON.
        # It is replaced with the actual Request later, if we can find it.
        request = OutgoingRequest(self, request_seq, command, "<unknown>")

        if not success:
            error_message = str(error_message)
            exc_type = MessageHandlingError
            if error_message.startswith(InvalidMessageError.PREFIX):
                error_message = error_message[len(InvalidMessageError.PREFIX):]
                exc_type = InvalidMessageError
            body = exc_type(error_message, request)

        response = Response(self, seq, request, body)

        if isinstance(body, dict):
            body.associate_with(response)

        try:
            with self:
                request = self._requests.pop(request_seq)
        except KeyError:
            response.isnt_valid(
                "request_seq={0} does not match any known request", request_seq
            )

        # Replace synthetic Request with real one.
        response.request = request
        if isinstance(response.body, MessageHandlingError):
            response.body.request = request

        request._handle_response(response)

    def on_disconnect(self):
        """Invoked when the channel is closed.

        No further message handlers will be invoked after this one returns.

        The default implementation ensures that any requests that are still outstanding
        automatically receive synthesized "no response" responses, and then invokes
        handlers.disconnect with no arguments, if it exists.
        """

        # Lock the channel to properly synchronize with the instant callback logic
        # in Request.on_response().
        with self:
            for request in self._requests.values():
                request.no_response()

        getattr(self.handlers, "disconnect", lambda: None)()

    def _process_incoming_message(self):
        # Set up a dedicated decoder for this message, to create MessageDict instances
        # for all JSON objects, and track them so that they can be later wired up to
        # the Message they belong to, once it is instantiated.
        def object_hook(d):
            d = MessageDict(None, d)
            if "seq" in d:
                self._prettify(d)
            d.associate_with = associate_with
            message_dicts.append(d)
            return d

        # A hack to work around circular dependency between messages, and instances of
        # MessageDict in their payload. We need to set message for all of them, but it
        # cannot be done until the actual Message is created - which happens after the
        # dicts are created during deserialization.
        #
        # So, upon deserialization, every dict in the message payload gets a method
        # that can be called to set MessageDict.message for _all_ dicts in that message.
        # Then, _on_request, _on_event, and _on_response can use it once they have parsed
        # the dicts, and created the appropriate Request/Event/Response instance.
        def associate_with(message):
            for d in message_dicts:
                d.message = message
                del d.associate_with

        message_dicts = []
        decoder = self.stream.json_decoder_factory(object_hook=object_hook)
        message = self.stream.read_json(decoder)
        assert isinstance(message, MessageDict)  # make sure stream used decoder

        try:
            return self._on_message(message)
        except EOFError:
            raise
        except Exception:
            raise log.exception(
                "Fatal error while processing message for {0}:\n\n{1!j}",
                self.name,
                message,
            )

    def _process_incoming_messages(self):
        try:
            log.debug("Starting message loop for {0}", self.name)
            while True:
                try:
                    self._process_incoming_message()
                except EOFError as ex:
                    log.debug("Exiting message loop for {0}: {1}", self.name, str(ex))
                    return False
        finally:
            try:
                self.on_disconnect()
            except Exception:
                log.exception("Error while processing disconnect for {0}", self.name)
                raise


class MessageHandlers(object):
    """A simple delegating message handlers object for use with JsonMessageChannel.
    For every argument provided, the object gets an attribute with the corresponding
    name and value.
    """

    def __init__(self, **kwargs):
        for name, func in kwargs.items():
            setattr(self, name, func)
