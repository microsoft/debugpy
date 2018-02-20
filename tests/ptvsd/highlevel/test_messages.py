import unittest

from _pydevd_bundle.pydevd_comm import (
    CMD_ADD_EXCEPTION_BREAK,
    CMD_CHANGE_VARIABLE,
    CMD_EVALUATE_EXPRESSION,
    CMD_GET_FRAME,
    CMD_GET_VARIABLE,
    CMD_LIST_THREADS,
    CMD_REMOVE_BREAK,
    CMD_REMOVE_EXCEPTION_BREAK,
    CMD_SEND_CURR_EXCEPTION_TRACE,
    CMD_SEND_CURR_EXCEPTION_TRACE_PROCEEDED,
    CMD_SET_BREAK,
    CMD_STEP_INTO,
    CMD_STEP_OVER,
    CMD_STEP_RETURN,
    CMD_THREAD_CREATE,
    CMD_THREAD_KILL,
    CMD_THREAD_RUN,
    CMD_THREAD_SUSPEND,
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
        addr = (None, 8888)
        with self.vsc.start(addr):
            with self.disconnect_when_done():
                self.set_debugger_response(CMD_VERSION, version)
                req = self.send_request('initialize', {
                    'adapterID': 'spam',
                })
                received = self.vsc.received

        self.assert_vsc_received(received, [
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
    PYDEVD_REQ = None
    PYDEVD_CMD = None

    def launched(self, port=8888):
        return super(NormalRequestTest, self).launched(port)

    def set_debugger_response(self, *args, **kwargs):
        if self.PYDEVD_REQ is None:
            return
        self.fix.set_debugger_response(
            self.PYDEVD_REQ,
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
        if self.PYDEVD_REQ is not None:
            return self.debugger_msgs.new_request(self.PYDEVD_REQ, *args)
        else:
            return self.debugger_msgs.new_request(self.PYDEVD_CMD, *args)


class ThreadsTests(NormalRequestTest, unittest.TestCase):

    COMMAND = 'threads'
    PYDEVD_REQ = CMD_LIST_THREADS

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
            received = self.vsc.received

        self.assert_vsc_received(received, [
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


# TODO: finish!
@unittest.skip('not finished')
class StackTraceTests(NormalRequestTest, unittest.TestCase):

    COMMAND = 'stackTrace'

    def test_basic(self):
        raise NotImplementedError


# TODO: finish!
@unittest.skip('not finished')
class ScopesTests(NormalRequestTest, unittest.TestCase):

    COMMAND = 'scopes'

    def test_basic(self):
        raise NotImplementedError


# TODO: finish!
@unittest.skip('not finished')
class VariablesTests(NormalRequestTest, unittest.TestCase):

    COMMAND = 'variables'
    PYDEVD_REQ = [
        CMD_GET_FRAME,
        CMD_GET_VARIABLE,
    ]

    def test_basic(self):
        raise NotImplementedError


# TODO: finish!
@unittest.skip('not finished')
class SetVariableTests(NormalRequestTest, unittest.TestCase):

    COMMAND = 'setVariable'
    PYDEVD_REQ = CMD_CHANGE_VARIABLE

    def test_basic(self):
        raise NotImplementedError


# TODO: finish!
@unittest.skip('not finished')
class EvaluateTests(NormalRequestTest, unittest.TestCase):

    COMMAND = 'evaluate'
    PYDEVD_REQ = CMD_EVALUATE_EXPRESSION

    def test_basic(self):
        raise NotImplementedError


# TODO: finish!
@unittest.skip('not finished')
class PauseTests(NormalRequestTest, unittest.TestCase):

    COMMAND = 'pause'
    PYDEVD_CMD = CMD_THREAD_SUSPEND

    def test_basic(self):
        raise NotImplementedError


# TODO: finish!
@unittest.skip('not finished')
class ContinueTests(NormalRequestTest, unittest.TestCase):

    COMMAND = 'continue'
    PYDEVD_CMD = CMD_THREAD_RUN

    def test_basic(self):
        raise NotImplementedError


# TODO: finish!
@unittest.skip('not finished')
class NextTests(NormalRequestTest, unittest.TestCase):

    COMMAND = 'next'
    PYDEVD_CMD = CMD_STEP_OVER

    def test_basic(self):
        raise NotImplementedError


# TODO: finish!
@unittest.skip('not finished')
class StepInTests(NormalRequestTest, unittest.TestCase):

    COMMAND = 'stepIn'
    PYDEVD_CMD = CMD_STEP_INTO

    def test_basic(self):
        raise NotImplementedError


# TODO: finish!
@unittest.skip('not finished')
class StepOutTests(NormalRequestTest, unittest.TestCase):

    COMMAND = 'stepOut'
    PYDEVD_CMD = CMD_STEP_RETURN

    def test_basic(self):
        raise NotImplementedError


# TODO: finish!
@unittest.skip('not finished')
class SetBreakpointsTests(NormalRequestTest, unittest.TestCase):

    COMMAND = 'setBreakpoints'
    PYDEVD_CMD = [
        [CMD_REMOVE_BREAK],
        [CMD_SET_BREAK],
    ]

    def test_basic(self):
        raise NotImplementedError


# TODO: finish!
@unittest.skip('not finished')
class SetExceptionBreakpointsTests(NormalRequestTest, unittest.TestCase):

    COMMAND = 'setExceptionBreakpoints'
    PYDEVD_CMD = [
        [CMD_REMOVE_EXCEPTION_BREAK],
        [CMD_ADD_EXCEPTION_BREAK],
    ]

    def test_basic(self):
        raise NotImplementedError


# TODO: finish!
@unittest.skip('not finished')
class ExceptionInfoTests(NormalRequestTest, unittest.TestCase):

    COMMAND = 'exceptionInfo'

    def test_basic(self):
        raise NotImplementedError


##################################
# handled PyDevd events

class PyDevdEventTest(RunningTest):

    CMD = None

    def test_basic(self):
        raise NotImplementedError


# TODO: finish!
@unittest.skip('not finished')
class ThreadCreateTests(PyDevdEventTest, unittest.TestCase):

    CMD = CMD_THREAD_CREATE


# TODO: finish!
@unittest.skip('not finished')
class ThreadKillTests(PyDevdEventTest, unittest.TestCase):

    CMD = CMD_THREAD_KILL


# TODO: finish!
@unittest.skip('not finished')
class ThreadSuspendTests(PyDevdEventTest, unittest.TestCase):

    CMD = CMD_THREAD_SUSPEND


# TODO: finish!
@unittest.skip('not finished')
class ThreadRunTests(PyDevdEventTest, unittest.TestCase):

    CMD = CMD_THREAD_RUN


# TODO: finish!
@unittest.skip('not finished')
class SendCurrExcTraceTests(PyDevdEventTest, unittest.TestCase):

    CMD = CMD_SEND_CURR_EXCEPTION_TRACE


# TODO: finish!
@unittest.skip('not finished')
class SendCurrExcTraceProceededTests(PyDevdEventTest, unittest.TestCase):

    CMD = CMD_SEND_CURR_EXCEPTION_TRACE_PROCEEDED
