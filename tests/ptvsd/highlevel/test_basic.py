import os
import sys

from _pydevd_bundle.pydevd_comm import (
    CMD_LIST_THREADS,
    CMD_RUN,
    CMD_VERSION,
)

from . import OS_ID, HighlevelTestCase


class LifecycleTests(HighlevelTestCase):
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

            # configuration
            pydevd.add_pending_response(CMD_RUN, '')
            req_config = {
                'type': 'request',
                'seq': self.next_vsc_seq(),
                'command': 'configurationDone',
                'arguments': {}
            }
            with vsc.wait_for_response(req_config):
                vsc.send_request(req_config)

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
                'request_seq': req_config['seq'],
                'command': 'configurationDone',
                'success': True,
                'message': '',
                'body': {},
            },
            {
                'type': 'event',
                'seq': 4,
                'event': 'process',
                'body': {
                    'name': sys.argv[0],
                    'systemProcessId': os.getpid(),
                    'isLocalProcess': True,
                    'startMethod': 'attach',
                },
            },
            {
                'type': 'response',
                'seq': 5,
                'request_seq': req_disconnect['seq'],
                'command': 'disconnect',
                'success': True,
                'message': '',
                'body': {},
            },
        ])
        pydevd.assert_received(self, [
            # (cmdid, seq, text)
            (
                CMD_VERSION,
                1000000000,
                '\t'.join(['1.1', OS_ID, 'ID']),
            ),
            (CMD_RUN, 1000000001, ''),
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

            # configuration
            pydevd.add_pending_response(CMD_RUN, '')
            req_config = {
                'type': 'request',
                'seq': self.next_vsc_seq(),
                'command': 'configurationDone',
                'arguments': {}
            }
            with vsc.wait_for_response(req_config):
                vsc.send_request(req_config)

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
                'request_seq': req_config['seq'],
                'command': 'configurationDone',
                'success': True,
                'message': '',
                'body': {},
            },
            {
                'type': 'event',
                'seq': 4,
                'event': 'process',
                'body': {
                    'name': sys.argv[0],
                    'systemProcessId': os.getpid(),
                    'isLocalProcess': True,
                    'startMethod': 'launch',
                },
            },
            {
                'type': 'response',
                'seq': 5,
                'request_seq': req_disconnect['seq'],
                'command': 'disconnect',
                'success': True,
                'message': '',
                'body': {},
            },
        ])
        pydevd.assert_received(self, [
            # (cmdid, seq, text)
            (
                CMD_VERSION,
                1000000000,
                '\t'.join(['1.1', OS_ID, 'ID']),
            ),
            (CMD_RUN, 1000000001, ''),
        ])


class RequestTests(HighlevelTestCase):
    """
    lifecycle (in order):

    initialize
    attach
    launch
    setBreakpoints
    setExceptionBreakpoints
    configurationDone
    disconnect

    normal operation:

    threads
    stackTrace
    scopes
    variables
    setVariable
    evaluate
    pause
    continue
    next
    stepIn
    stepOut
    setBreakpoints
    setExceptionBreakpoints
    exceptionInfo
    """

    def test_initialize(self):
        vsc, pydevd = self.new_fake()

        with vsc.start(None, 8888):
            try:
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
            finally:
                self.disconnect(vsc)
                vsc._received.pop(-1)

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
        text = '\t'.join(['1.1', OS_ID, 'ID'])
        pydevd.assert_received(self, [
            (CMD_VERSION, seq, text),
        ])

    def test_threads(self):
        vsc, pydevd = self.new_fake()
        with self.launched(vsc, pydevd):
            pydevd.add_pending_response(CMD_LIST_THREADS, """
                <xml>
                <thread name="spam" id="10" />
                <thread name="pydevd.spam" id="11" />
                <thread name="" id="12" />
                </xml>
            """.strip().replace('\n', ''))
            req = {
                'type': 'request',
                'seq': self.next_vsc_seq(),
                'command': 'threads',
                'arguments': {},
            }
            with vsc.wait_for_response(req):
                vsc.send_request(req)

        self.maxDiff = None
        self.assertFalse(pydevd.failures)
        self.assertFalse(vsc.failures)
        vsc.assert_received(self, [
            {
                'type': 'response',
                'seq': 5,
                'request_seq': req['seq'],
                'command': 'threads',
                'success': True,
                'message': '',
                'body': {
                    'threads': [
                        {'id': 1, 'name': 'spam'},
                        {'id': 3, 'name': ''},
                    ],
                },
            },
        ])
        pydevd.assert_received(self, [
            # (cmdid, seq, text)
            (CMD_LIST_THREADS, 1000000002, ''),
        ])
