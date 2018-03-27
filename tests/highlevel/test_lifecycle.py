#import os
#import sys
import unittest

from _pydevd_bundle.pydevd_comm import (
    CMD_REDIRECT_OUTPUT,
    CMD_RUN,
    CMD_VERSION,
)

from . import OS_ID, HighlevelTest, HighlevelFixture


# TODO: Make sure we are handling the following properly:
#  * initialize args
#  * capabilities (sent in a response)
#  * setting breakpoints during config
#  * sending an "exit" event.


class LifecycleTests(HighlevelTest, unittest.TestCase):
    """
    See https://code.visualstudio.com/docs/extensionAPI/api-debugging#_the-vs-code-debug-protocol-in-a-nutshell
    """  # noqa

    class FIXTURE(HighlevelFixture):
        lifecycle = None  # Make sure we don't cheat.

    def test_attach(self):
        version = self.debugger.VERSION
        addr = (None, 8888)
        with self.vsc.start(addr):
            with self.vsc.wait_for_event('initialized'):
                # initialize
                self.set_debugger_response(CMD_VERSION, version)
                req_initialize = self.send_request('initialize', {
                    'adapterID': 'spam',
                })

                # attach
                req_attach = self.send_request('attach')

            # configuration
            req_config = self.send_request('configurationDone')

            # Normal ops would go here.

            # end
            req_disconnect = self.send_request('disconnect')
        # An "exited" event comes once self.vsc closes.

        self.assert_received(self.vsc, [
            self.new_response(req_initialize, **dict(
                supportsExceptionInfoRequest=True,
                supportsConfigurationDoneRequest=True,
                supportsConditionalBreakpoints=True,
                supportsSetVariable=True,
                supportsValueFormattingOptions=True,
                supportsExceptionOptions=True,
                exceptionBreakpointFilters=[
                    {
                        'filter': 'raised',
                        'label': 'Raised Exceptions',
                        'default': 'false'
                    },
                    {
                        'filter': 'uncaught',
                        'label': 'Uncaught Exceptions',
                        'default': 'true'
                    },
                ],
                supportsEvaluateForHovers=True,
                supportsSetExpression=True,
                supportsModulesRequest=True,
            )),
            self.new_event('initialized'),
            self.new_response(req_attach),
            self.new_response(req_config),
            #self.new_event('process', **dict(
            #    name=sys.argv[0],
            #    systemProcessId=os.getpid(),
            #    isLocalProcess=True,
            #    startMethod='attach',
            #)),
            self.new_response(req_disconnect),
            self.new_event('exited', exitCode=0),
        ])
        self.assert_received(self.debugger, [
            self.debugger_msgs.new_request(CMD_VERSION,
                                           *['1.1', OS_ID, 'ID']),
            self.debugger_msgs.new_request(CMD_REDIRECT_OUTPUT),
            self.debugger_msgs.new_request(CMD_RUN),
        ])

    def test_launch(self):
        version = self.debugger.VERSION
        addr = (None, 8888)
        with self.vsc.start(addr):
            with self.vsc.wait_for_event('initialized'):
                # initialize
                self.set_debugger_response(CMD_VERSION, version)
                req_initialize = self.send_request('initialize', {
                    'adapterID': 'spam',
                })

                # launch
                req_launch = self.send_request('launch')

            # configuration
            req_config = self.send_request('configurationDone')

            # Normal ops would go here.

            # end
            req_disconnect = self.send_request('disconnect')
        # An "exited" event comes once self.vsc closes.

        self.assert_received(self.vsc, [
            self.new_response(req_initialize, **dict(
                supportsExceptionInfoRequest=True,
                supportsConfigurationDoneRequest=True,
                supportsConditionalBreakpoints=True,
                supportsSetVariable=True,
                supportsValueFormattingOptions=True,
                supportsExceptionOptions=True,
                exceptionBreakpointFilters=[
                    {
                        'filter': 'raised',
                        'label': 'Raised Exceptions',
                        'default': 'false'
                    },
                    {
                        'filter': 'uncaught',
                        'label': 'Uncaught Exceptions',
                        'default': 'true'
                    },
                ],
                supportsEvaluateForHovers=True,
                supportsSetExpression=True,
                supportsModulesRequest=True,
            )),
            self.new_event('initialized'),
            self.new_response(req_launch),
            self.new_response(req_config),
            #self.new_event('process', **dict(
            #    name=sys.argv[0],
            #    systemProcessId=os.getpid(),
            #    isLocalProcess=True,
            #    startMethod='launch',
            #)),
            self.new_event('exited', exitCode=0),
            self.new_event('terminated'),
            self.new_response(req_disconnect),
        ])
        self.assert_received(self.debugger, [
            self.debugger_msgs.new_request(CMD_VERSION,
                                           *['1.1', OS_ID, 'ID']),
            self.debugger_msgs.new_request(CMD_REDIRECT_OUTPUT),
            self.debugger_msgs.new_request(CMD_RUN),
        ])
