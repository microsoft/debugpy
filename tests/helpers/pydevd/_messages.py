try:
    import urllib.parse as urllib
except ImportError:
    import urllib

from _pydevd_bundle import pydevd_xml
from _pydevd_bundle.pydevd_comm import (
    CMD_SEND_CURR_EXCEPTION_TRACE,
)

from tests.helpers.protocol import MessageCounters
from ._fake import FakePyDevd


class PyDevdMessages(object):

    protocol = FakePyDevd.PROTOCOL

    def __init__(self,
                 request_seq=1000000000,  # ptvsd requests to pydevd
                 response_seq=0,  # PyDevd responses/events to ptvsd
                 event_seq=None,
                 ):
        self.counters = MessageCounters(
            request_seq,
            response_seq,
            event_seq,
        )

    def __getattr__(self, name):
        return getattr(self.counters, name)

    def new_request(self, cmdid, *args, **kwargs):
        """Return a new PyDevd request message."""
        seq = kwargs.pop('seq', None)
        if seq is None:
            seq = self.counters.next_request()
        return self._new_message(cmdid, seq, args, **kwargs)

    def new_response(self, req, *args):
        """Return a new VSC response message."""
        #seq = kwargs.pop('seq', None)
        #if seq is None:
        #    seq = next(self.response_seq)
        req = self.protocol.parse(req)
        return self._new_message(req.cmdid, req.seq, args)

    def new_event(self, cmdid, *args, **kwargs):
        """Return a new VSC event message."""
        seq = kwargs.pop('seq', None)
        if seq is None:
            seq = self.counters.next_event()
        return self._new_message(cmdid, seq, args, **kwargs)

    def _new_message(self, cmdid, seq, args=()):
        text = '\t'.join(args)
        msg = (cmdid, seq, text)
        return self.protocol.parse(msg)

    def format_threads(self, *threads):
        text = '<xml>'
        for thread in threads:  # (tid, tname)
            text += '<thread id="{}" name="{}" />'.format(*thread)
        text += '</xml>'
        return text

    def format_frames(self, threadid, reason, *frames):
        text = '<xml>'
        text += '<thread id="{}" stop_reason="{}">'.format(threadid, reason)
        fmt = '<frame id="{}" name="{}" file="{}" line="{}" />'
        for frame in frames:  # (fid, func, filename, line)
            text += fmt.format(*frame)
        text += '</thread>'
        text += '</xml>'
        return text

    def format_variables(self, *variables):
        text = '<xml>'
        for name, value in variables:
            if isinstance(value, str) and value.startswith('err:'):
                value = pydevd_xml.ExceptionOnEvaluate(value[4:])
            text += pydevd_xml.var_to_xml(value, name)
        text += '</xml>'
        return urllib.quote(text)

    def format_exception(self, threadid, exc, frame):
        frameid, _, _, _ = frame
        name = pydevd_xml.make_valid_xml_value(type(exc).__name__)
        description = pydevd_xml.make_valid_xml_value(str(exc))

        info = '<xml>'
        info += '<thread id="{}" />'.format(threadid)
        info += '</xml>'
        return '{}\t{}\t{}\t{}'.format(
            frameid,
            name or 'exception: type unknown',
            description or 'exception: no description',
            self.format_frames(
                threadid,
                CMD_SEND_CURR_EXCEPTION_TRACE,
                frame,
            ),
        )

    def format_exception_details(self, threadid, exc, *frames):
        name = pydevd_xml.make_valid_xml_value(str(type(exc)))
        if hasattr(exc, 'args') and len(exc.args) > 0:
            desc = str(exc.args[0])
        else:
            desc = str(exc)
        desc = pydevd_xml.make_valid_xml_value(desc)
        info = '<xml>'
        info += '<thread id="{}" exc_type="{}" exc_desc="{}" >'.format(
            threadid, name, desc)
        fmt = '<frame id="{}" name="{}" file="{}" line="{}" />'
        for frame in frames:  # (fid, func, filename, line)
            info += fmt.format(*frame)
        info += '</thread></xml>'
        return info
