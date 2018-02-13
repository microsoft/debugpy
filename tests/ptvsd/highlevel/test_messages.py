import unittest

from _pydevd_bundle.pydevd_comm import (
    CMD_LIST_THREADS,
    CMD_VERSION,
)

from . import OS_ID, RunningTest


# TODO: Make sure we are handling all args properly and sending the
# correct response/event bpdies.

"""
lifecycle (in order), tested via test_lifecycle.py:

initialize
attach
launch
(setBreakpoints)
(setExceptionBreakpoints)
configurationDone
(normal ops)
disconnect

Note that setFunctionBreakpoints may also be sent during
configuration, but we do not support function breakpoints.

normal operations (supported-only):

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

handled PyDevd events:

CMD_THREAD_CREATE
CMD_THREAD_KILL
CMD_THREAD_SUSPEND
CMD_THREAD_RUN
CMD_SEND_CURR_EXCEPTION_TRACE
CMD_SEND_CURR_EXCEPTION_TRACE_PROCEEDED
"""


##################################
# lifecycle requests

class LifecycleTest(RunningTest):
    pass


class InitializeTests(LifecycleTest, unittest.TestCase):

    @unittest.skip('tested via test_lifecycle.py')
    def test_basic(self):
        version = self.debugger.VERSION
        with self.vsc.start(None, 8888):
            with self.disconnect_when_done():
                self.set_debugger_response(CMD_VERSION, version)
                req = self.send_request('initialize', {
                    'adapterID': 'spam',
                })

        self.assert_received(self.vsc, [
            self.new_response(req, **dict(
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
            )),
            self.new_event(1, 'initialized'),
        ])
        self.assert_received(self.debugger, [
            self.debugger_msgs.new_request(CMD_VERSION,
                                           *['1.1', OS_ID, 'ID']),
        ])


##################################
# "normal operation" requests

class NormalRequestTest(RunningTest):

    COMMAND = None
    PYDEVD_CMD = None

    def launched(self, port=8888):
        return super(NormalRequestTest, self).launched(port)

    def set_debugger_response(self, *args, **kwargs):
        if self.PYDEVD_CMD is None:
            return
        self.fix.set_debugger_response(
            self.PYDEVD_CMD,
            self.pydevd_payload(*args, **kwargs),
        )

    def pydevd_payload(self, *args, **kwargs):
        return ''

    def send_request(self, **args):
        self.req = self.fix.send_request(self.COMMAND, args)

    def expected_response(self, **body):
        return self.new_response(
            self.req,
            **body
        )

    def expected_pydevd_request(self, *args):
        return self.debugger_msgs.new_request(self.PYDEVD_CMD, *args)


class ThreadsTests(NormalRequestTest, unittest.TestCase):

    COMMAND = 'threads'
    PYDEVD_CMD = CMD_LIST_THREADS

    def pydevd_payload(self, *threads):
        text = '<xml>'
        for tid, tname in threads:
            text += '<thread name="{}" id="{}" />'.format(tname, tid)
        text += '</xml>'
        return text

    def test_basic(self):
        with self.launched():
            self.set_debugger_response(
                (10, 'spam'),
                (11, 'pydevd.eggs'),
                (12, ''),
            )
            self.send_request()

        self.assert_received(self.vsc, [
            self.expected_response(
                threads=[
                    {'id': 1, 'name': 'spam'},
                    # Threads named 'pydevd.*' are ignored.
                    {'id': 3, 'name': ''},
                ],
            ),
            # no events
        ])
        self.assert_received(self.debugger, [
            self.expected_pydevd_request(),
        ])
