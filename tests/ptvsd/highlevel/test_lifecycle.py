import os
import sys

from _pydevd_bundle.pydevd_comm import (
    CMD_RUN,
    CMD_VERSION,
)

from . import OS_ID, HighlevelTestCase


# TODO: Make sure we are handling the following properly:
#  * initialize args
#  * capabilities (sent in a response)
#  * setting breakpoints during config
#  * sending an "exit" event.


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
                req_initialize = self.new_request('initialize',
                    adapterID='spam',
                )  # noqa
                with vsc.wait_for_response(req_initialize):
                    vsc.send_request(req_initialize)

                # attach
                req_attach = self.new_request('attach')
                with vsc.wait_for_response(req_attach):
                    vsc.send_request(req_attach)

            # configuration
            pydevd.add_pending_response(CMD_RUN, '')
            req_config = self.new_request('configurationDone')
            with vsc.wait_for_response(req_config):
                vsc.send_request(req_config)

            # end
            req_disconnect = self.new_request('disconnect')
            with vsc.wait_for_response(req_disconnect):
                vsc.send_request(req_disconnect)

        self.assertFalse(pydevd.failures)
        self.assertFalse(vsc.failures)
        vsc.assert_received(self, [
            self.new_response(0, req_initialize,
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
            ),  # noqa
            self.new_event(1, 'initialized'),
            self.new_response(2, req_attach),
            self.new_response(3, req_config),
            self.new_event(4, 'process',
                name=sys.argv[0],
                systemProcessId=os.getpid(),
                isLocalProcess=True,
                startMethod='attach',
            ),  # noqa
            self.new_response(5, req_disconnect),
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
                req_initialize = self.new_request('initialize',
                    adapterID='spam',
                )  # noqa
                with vsc.wait_for_response(req_initialize):
                    vsc.send_request(req_initialize)

                # launch
                req_launch = self.new_request('launch')
                with vsc.wait_for_response(req_launch):
                    vsc.send_request(req_launch)

            # configuration
            pydevd.add_pending_response(CMD_RUN, '')
            req_config = self.new_request('configurationDone')
            with vsc.wait_for_response(req_config):
                vsc.send_request(req_config)

            # end
            req_disconnect = self.new_request('disconnect')
            with vsc.wait_for_response(req_disconnect):
                vsc.send_request(req_disconnect)

        self.assertFalse(pydevd.failures)
        self.assertFalse(vsc.failures)
        vsc.assert_received(self, [
            self.new_response(0, req_initialize,
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
            ),  # noqa
            self.new_event(1, 'initialized'),
            self.new_response(2, req_launch),
            self.new_response(3, req_config),
            self.new_event(4, 'process',
                name=sys.argv[0],
                systemProcessId=os.getpid(),
                isLocalProcess=True,
                startMethod='launch',
            ),  # noqa
            self.new_response(5, req_disconnect),
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
