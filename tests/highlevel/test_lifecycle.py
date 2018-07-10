import os
import ptvsd
import sys
import unittest

from _pydevd_bundle.pydevd_comm import (
    CMD_REDIRECT_OUTPUT,
    CMD_RUN,
    CMD_VERSION,
    CMD_SET_PROJECT_ROOTS,
)

from . import (
    OS_ID,
    HighlevelTest,
    HighlevelFixture,
)


from ptvsd.wrapper import INITIALIZE_RESPONSE

# TODO: Make sure we are handling the following properly:
#  * initialize args
#  * capabilities (sent in a response)
#  * setting breakpoints during config
#  * sending an "exit" event.


def _get_project_dirs():
    vendored_pydevd = os.path.sep + \
                      os.path.join('ptvsd', '_vendored', 'pydevd')
    ptvsd_path = os.path.sep + 'ptvsd'

    project_dirs = []
    for path in sys.path + [os.getcwd()]:
        is_stdlib = False
        norm_path = os.path.normcase(path)
        if path.endswith(ptvsd_path) or \
            path.endswith(vendored_pydevd):
            is_stdlib = True
        else:
            for prefix in ptvsd.wrapper.STDLIB_PATH_PREFIXES:
                if norm_path.startswith(prefix):
                    is_stdlib = True
                    break

        if not is_stdlib and len(path) > 0:
            project_dirs.append(path)

    return '\t'.join(project_dirs)


class LifecycleTests(HighlevelTest, unittest.TestCase):
    """
    See https://code.visualstudio.com/docs/extensionAPI/api-debugging#_the-vs-code-debug-protocol-in-a-nutshell
    """  # noqa

    class FIXTURE(HighlevelFixture):
        lifecycle = None  # Make sure we don't cheat.

    def attach(self, expected_os_id, attach_args):
        version = self.debugger.VERSION
        self.fix.debugger.binder.singlesession = False
        addr = (None, 8888)
        daemon = self.vsc.start(addr)
        with self.vsc.wait_for_event('output'):
            daemon.wait_until_connected()
        try:
            with self.vsc.wait_for_event('initialized'):
                # initialize
                self.set_debugger_response(CMD_VERSION, version)
                req_initialize = self.send_request('initialize', {
                    'adapterID': 'spam',
                })

                # attach
                req_attach = self.send_request('attach', attach_args)

            # configuration
            with self._fix.wait_for_events(['process']):
                req_config = self.send_request('configurationDone')

            # Normal ops would go here.

            # end
            #req_disconnect = self.send_request('disconnect')
        finally:
            received = self.vsc.received
            with self._fix.wait_for_events(['exited', 'terminated']):
                self.fix.close_ptvsd()
            daemon.close()
            #self.fix.close_ptvsd()

        self.assert_vsc_received(received, [
            self.new_event(
                'output',
                category='telemetry',
                output='ptvsd',
                data={'version': ptvsd.__version__}),
            self.new_response(req_initialize, **INITIALIZE_RESPONSE),
            self.new_event('initialized'),
            self.new_response(req_attach),
            self.new_response(req_config),
            self.new_event('process', **dict(
               name=sys.argv[0],
               systemProcessId=os.getpid(),
               isLocalProcess=True,
               startMethod='attach',
            )),
        ])
        self.assert_received(self.debugger, [
            self.debugger_msgs.new_request(CMD_VERSION,
                                           *['1.1', expected_os_id, 'ID']),
            self.debugger_msgs.new_request(CMD_REDIRECT_OUTPUT),
            self.debugger_msgs.new_request(CMD_SET_PROJECT_ROOTS,
                                           _get_project_dirs()),
            self.debugger_msgs.new_request(CMD_RUN),
        ])

    def test_attach(self):
        self.attach(expected_os_id=OS_ID, attach_args={})

    @unittest.skip('not implemented')
    def test_attach_exit_during_session(self):
        # TODO: Ensure we see the "terminated" and "exited" events.
        raise NotImplementedError

    def test_attach_from_unix_os_vsc(self):
        attach_args = {'debugOptions': ['UnixClient']}
        self.attach(expected_os_id='UNIX', attach_args=attach_args)

    def test_attach_from_unix_os(self):
        attach_args = {'options': 'CLIENT_OS_TYPE=UNIX'}
        self.attach(expected_os_id='UNIX', attach_args=attach_args)

    def test_attach_from_win_os_vsc(self):
        attach_args = {'debugOptions': ['WindowsClient']}
        self.attach(expected_os_id='WINDOWS', attach_args=attach_args)

    def test_attach_from_windows_os(self):
        attach_args = {'options': 'CLIENT_OS_TYPE=WINDOWS'}
        self.attach(expected_os_id='WINDOWS', attach_args=attach_args)

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
            self.wait_for_pydevd('version', 'redirect-output',
                                 'run', 'set_project_roots')

            # Normal ops would go here.

            # end
            #with self.fix.wait_for_events(['exited', 'terminated']):
            req_disconnect = self.send_request('disconnect')

        self.assert_received(self.vsc, [
            self.new_event(
                'output',
                category='telemetry',
                output='ptvsd',
                data={'version': ptvsd.__version__}),
            self.new_response(req_initialize, **INITIALIZE_RESPONSE),
            self.new_event('initialized'),
            self.new_response(req_launch),
            self.new_response(req_config),
            #self.new_event('process', **dict(
            #    name=sys.argv[0],
            #    systemProcessId=os.getpid(),
            #    isLocalProcess=True,
            #    startMethod='launch',
            #)),
            #self.new_event('exited', exitCode=0),
            #self.new_event('terminated'),
            self.new_response(req_disconnect),
        ])
        self.assert_received(self.debugger, [
            self.debugger_msgs.new_request(CMD_VERSION,
                                           *['1.1', OS_ID, 'ID']),
            self.debugger_msgs.new_request(CMD_REDIRECT_OUTPUT),
            self.debugger_msgs.new_request(CMD_SET_PROJECT_ROOTS,
                                           _get_project_dirs()),
            self.debugger_msgs.new_request(CMD_RUN),
        ])
