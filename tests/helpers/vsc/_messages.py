from tests.helpers.protocol import MessageCounters
from ._fake import FakeVSC


class VSCMessages(object):

    protocol = FakeVSC.PROTOCOL

    def __init__(self,
                 request_seq=0,  # VSC requests to ptvsd
                 response_seq=0,  # ptvsd responses/events to VSC
                 event_seq=None,
                 ):
        self.counters = MessageCounters(
            request_seq,
            response_seq,
            event_seq,
        )

    def __getattr__(self, name):
        return getattr(self.counters, name)

    def new_request(self, command, seq=None, **args):
        """Return a new VSC request message."""
        if seq is None:
            seq = self.counters.next_request()
        return {
            'type': 'request',
            'seq': seq,
            'command': command,
            'arguments': args,
        }

    def new_response(self, req, seq=None, **body):
        """Return a new VSC response message."""
        return self._new_response(req, None, seq, body)

    def new_failure(self, req, err, seq=None, **body):
        """Return a new VSC response message."""
        return self._new_response(req, err, body=body)

    def _new_response(self, req, err=None, seq=None, body=None):
        if seq is None:
            seq = self.counters.next_response()
        return {
            'type': 'response',
            'seq': seq,
            'request_seq': req['seq'],
            'command': req['command'],
            'success': err is None,
            'message': err or '',
            'body': body,
        }

    def new_event(self, eventname, seq=None, **body):
        """Return a new VSC event message."""
        if seq is None:
            seq = self.counters.next_event()
        if eventname == 'stopped':
            body['allThreadsStopped'] = True
        return {
            'type': 'event',
            'seq': seq,
            'event': eventname,
            'body': body,
        }
