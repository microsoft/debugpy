from _pydevd_bundle.pydevd_comm import (
    CMD_VERSION,
)

import ptvsd.wrapper as _ptvsd
from ._pydevd import parse_message, encode_message, iter_messages, Message
from tests.helpers import protocol, socket


PROTOCOL = protocol.MessageProtocol(
    parse=parse_message,
    encode=encode_message,
    iter=iter_messages,
)


def _bind(address):
    connect, remote = socket.bind(address)

    def connect(_connect=connect):
        client, server = _connect()
        pydevd, _, _ = _ptvsd._start(client, server)
        return socket.Connection(pydevd, server)
    return connect, remote


class Started(protocol.Started):

    def send_response(self, msg):
        self.wait_until_connected()
        return self.fake.send_response(msg)

    def send_event(self, msg):
        self.wait_until_connected()
        return self.fake.send_event(msg)


class FakePyDevd(protocol.Daemon):
    """A testing double for PyDevd.

    Note that you have the option to provide a handler function.  This
    function will be called for each received message, with two args:
    the received message and the fake's "send_message" method.  If
    appropriate, it may call send_message() in response to the received
    message, along with doing anything else it needs to do.  Any
    exceptions raised by the handler are recorded but otherwise ignored.

    Example usage:

      >>> fake = FakePyDevd('127.0.0.1', 8888)
      >>> with fake.start('127.0.0.1', 8888):
      ...   fake.send_response(b'101\t1\t')
      ...   fake.send_event(b'900\t2\t')
      ... 
      >>> fake.assert_received(testcase, [
      ...   b'101\t1\t',  # the "run" request
      ...   # some other requests
      ... ])
      >>> 

    A description of the protocol:
      https://github.com/fabioz/PyDev.Debugger/blob/master/_pydevd_bundle/pydevd_comm.py
    """  # noqa

    STARTED = Started

    PROTOCOL = PROTOCOL
    VERSION = '1.1.1'

    @classmethod
    def validate_message(cls, msg):
        """Ensure the message is legitimate."""
        # TODO: Check the message.

    @classmethod
    def handle_request(cls, req, send_message, handler=None):
        """The default message handler."""
        if handler is not None:
            handler(req, send_message)

        resp = cls._get_response(req)
        if resp is not None:
            send_message(resp)

    @classmethod
    def _get_response(cls, req):
        try:
            cmdid, seq, _ = req
        except (IndexError, ValueError):
            req = req.msg
            cmdid, seq, _ = req

        if cmdid == CMD_VERSION:
            return Message(CMD_VERSION, seq, cls.VERSION)
        else:
            return None

    def __init__(self, handler=None):
        super(FakePyDevd, self).__init__(
            _bind,
            PROTOCOL,
            (lambda msg, send: self.handle_request(msg, send, handler)),
        )

    def send_response(self, msg):
        """Send a response message to the adapter (ptvsd)."""
        # XXX Ensure it's a response?
        return self._send_message(msg)

    def send_event(self, msg):
        """Send an event message to the adapter (ptvsd)."""
        # XXX Ensure it's a request?
        return self.send_message(msg)

    def add_pending_response(self, cmdid, text, reqid=None):
        """Add a response for a request."""
        if reqid is None:
            reqid = cmdid
        respid = cmdid

        def handle_request(req, send_message):
            try:
                cmdid, seq, _ = req
            except (IndexError, ValueError):
                req = req.msg
                cmdid, seq, _ = req
            if cmdid != reqid:
                return False
            resp = Message(respid, seq, text)
            send_message(resp)
            return True
        self.add_handler(handle_request)
