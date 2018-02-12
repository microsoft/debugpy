from _pydevd_bundle.pydevd_comm import (
    CMD_VERSION,
)

from . import OS_ID, HighlevelTestCase


class LivecycleTests(HighlevelTestCase):
    """
    See https://code.visualstudio.com/docs/extensionAPI/api-debugging#_the-vs-code-debug-protocol-in-a-nutshell
    """  # noqa

    def test_attach(self):
        vsc, pydevd = self.new_fake()

        with vsc.start(None, 8888):
            with vsc.wait_for_event('initialized'):
                # initialize
                pydevd.add_pending_response(CMD_VERSION, pydevd.VERSION)
                req_initialize = {
                    'type': 'request',
                    'seq': self.next_vsc_seq(),
                    'command': 'initialize',
                    'arguments': {
                        'adapterID': 'spam',
                    },
                }
                with vsc.wait_for_response(req_initialize):
                    vsc.send_request(req_initialize)

                # attach
                req_attach = {
                    'type': 'request',
                    'seq': self.next_vsc_seq(),
                    'command': 'attach',
                    'arguments': {},
                }
                with vsc.wait_for_response(req_attach):
                    vsc.send_request(req_attach)

            # end
            req_disconnect = {
                'type': 'request',
                'seq': self.next_vsc_seq(),
                'command': 'disconnect',
                'arguments': {},
            }
            with vsc.wait_for_response(req_disconnect):
                vsc.send_request(req_disconnect)

        self.assertFalse(pydevd.failures)
        self.assertFalse(vsc.failures)
        vsc.assert_received(self, [
            {
                'type': 'response',
                'seq': 0,
                'request_seq': req_initialize['seq'],
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
            {
                'type': 'response',
                'seq': 2,
                'request_seq': req_attach['seq'],
                'command': 'attach',
                'success': True,
                'message': '',
                'body': {},
            },
            {
                'type': 'response',
                'seq': 3,
                'request_seq': req_disconnect['seq'],
                'command': 'disconnect',
                'success': True,
                'message': '',
                'body': {},
            },
        ])
        seq = 1000000000
        pydevd.assert_received(self, [
            '{}\t{}\t1.1\t{}\tID'.format(CMD_VERSION, seq, OS_ID),
        ])

    def test_launch(self):
        vsc, pydevd = self.new_fake()

        with vsc.start(None, 8888):
            with vsc.wait_for_event('initialized'):
                # initialize
                pydevd.add_pending_response(CMD_VERSION, pydevd.VERSION)
                req_initialize = {
                    'type': 'request',
                    'seq': self.next_vsc_seq(),
                    'command': 'initialize',
                    'arguments': {
                        'adapterID': 'spam',
                    },
                }
                with vsc.wait_for_response(req_initialize):
                    vsc.send_request(req_initialize)

                # launch
                req_launch = {
                    'type': 'request',
                    'seq': self.next_vsc_seq(),
                    'command': 'launch',
                    'arguments': {},
                }
                with vsc.wait_for_response(req_launch):
                    vsc.send_request(req_launch)

            # end
            req_disconnect = {
                'type': 'request',
                'seq': self.next_vsc_seq(),
                'command': 'disconnect',
                'arguments': {},
            }
            with vsc.wait_for_response(req_disconnect):
                vsc.send_request(req_disconnect)

        self.assertFalse(pydevd.failures)
        self.assertFalse(vsc.failures)
        vsc.assert_received(self, [
            {
                'type': 'response',
                'seq': 0,
                'request_seq': req_initialize['seq'],
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
            {
                'type': 'response',
                'seq': 2,
                'request_seq': req_launch['seq'],
                'command': 'launch',
                'success': True,
                'message': '',
                'body': {},
            },
            {
                'type': 'response',
                'seq': 3,
                'request_seq': req_disconnect['seq'],
                'command': 'disconnect',
                'success': True,
                'message': '',
                'body': {},
            },
        ])
        seq = 1000000000
        pydevd.assert_received(self, [
            '{}\t{}\t1.1\t{}\tID'.format(CMD_VERSION, seq, OS_ID),
        ])


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
