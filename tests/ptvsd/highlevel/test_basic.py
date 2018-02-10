import threading
import unittest

from _pydevd_bundle.pydevd_comm import (
    CMD_VERSION,
)

from tests.helpers.pydevd import FakePyDevd
from . import OS_ID, HighlevelTestCase


@unittest.skip('finish!')
class LivecycleTests(HighlevelTestCase):
    """
    See https://code.visualstudio.com/docs/extensionAPI/api-debugging#_the-vs-code-debug-protocol-in-a-nutshell
    """  # noqa

    def test_startup(self):
        raise NotImplementedError

    def test_shutdown(self):
        raise NotImplementedError


class MessageTests(HighlevelTestCase):

    def test_initialize(self):
        self.pseq = -1
        plock = threading.Lock()
        plock.acquire()

        def handle_pydevd(msg, _):
            try:
                seq = msg.bytes.split(b'\t')[1]
            except IndexError:
                return
            self.pseq = int(seq.decode('utf-8'))
            plock.release()
        pydevd = FakePyDevd(handle_pydevd)

        self.num_left_vsc = 2
        vlock = threading.Lock()
        vlock.acquire()

        def handle_vsp(msg, _):
            if self.num_left_vsc == 0:
                return
            self.num_left_vsc -= 1
            if self.num_left_vsc == 0:
                vlock.release()
        vsc, _ = self.new_fake(pydevd, handle_vsp)
        with vsc.start(None, 8888):
            vsc.send_request({
                'type': 'request',
                'seq': 42,
                'command': 'initialize',
                'arguments': {
                    'adapterID': 'spam',
                },
            })
            plock.acquire(timeout=1)
            pydevd.send_response(
                '{}\t{}\t<VERSION>'.format(CMD_VERSION, self.pseq))
            plock.release()
            vlock.acquire(timeout=1)  # wait for 2 messages to come back
            vlock.release()

        self.maxDiff = None
        self.assertFalse(pydevd.failures)
        self.assertFalse(vsc.failures)
        vsc.assert_received(self, [
            {
                'type': 'response',
                'seq': 0,
                'request_seq': 42,
                'command': 'initialize',
                'success': True,
                'message': '',
                'body': dict(
                    supportsExceptionInfoRequest=True,
                    supportsConfigurationDoneRequest=True,
                    supportsConditionalBreakpoints=True,
                    supportsSetVariable=True,
                    supportsExceptionOptions=True,
                    exceptionBreakpointFilters=[
                        {
                            'filter': 'raised',
                            'label': 'Raised Exceptions',
                            'default': 'true'
                        },
                        {
                            'filter': 'uncaught',
                            'label': 'Uncaught Exceptions',
                            'default': 'true'
                        },
                    ],
                ),
            },
            {
                'type': 'event',
                'seq': 1,
                'event': 'initialized',
                'body': {},
            },
        ])
        seq = 1000000000
        pydevd.assert_received(self, [
            '{}\t{}\t1.1\t{}\tID'.format(CMD_VERSION, seq, OS_ID),
        ])
