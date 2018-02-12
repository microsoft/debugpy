import unittest

from _pydevd_bundle.pydevd_comm import (
    CMD_VERSION,
)

from . import OS_ID, HighlevelTestCase


@unittest.skip('finish!')
class LivecycleTests(HighlevelTestCase):
    """
    See https://code.visualstudio.com/docs/extensionAPI/api-debugging#_the-vs-code-debug-protocol-in-a-nutshell
    """  # noqa

    def test_attach(self):
        raise NotImplementedError

    def test_launch(self):
        raise NotImplementedError

    def test_shutdown(self):
        raise NotImplementedError


class MessageTests(HighlevelTestCase):

    def test_initialize(self):
        vsc, pydevd = self.new_fake()

        with vsc.start(None, 8888):
            pydevd.add_pending_response(CMD_VERSION, pydevd.VERSION)
            req = {
                'type': 'request',
                'seq': self.next_vsc_seq(),
                'command': 'initialize',
                'arguments': {
                    'adapterID': 'spam',
                },
            }
            with vsc.wait_for_response(req):
                vsc.send_request(req)

        self.maxDiff = None
        self.assertFalse(pydevd.failures)
        self.assertFalse(vsc.failures)
        vsc.assert_received(self, [
            {
                'type': 'response',
                'seq': 0,
                'request_seq': req['seq'],
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
