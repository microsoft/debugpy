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
    CMD_RETURN,
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
            self.new_debugger_request(CMD_VERSION,
                                      *['1.1', OS_ID, 'ID']),
        ])


##################################
# "normal operation" requests

class NormalRequestTest(RunningTest):

    COMMAND = None
    PYDEVD_CMD = None
    PYDEVD_RESP = True

    def launched(self, port=8888, **kwargs):
        return super(NormalRequestTest, self).launched(port, **kwargs)

    def set_debugger_response(self, *args, **kwargs):
        if self.PYDEVD_RESP is None:
            return
        if self.PYDEVD_RESP is True:
            self.PYDEVD_RESP = self.PYDEVD_CMD
        self.fix.set_debugger_response(
            self.PYDEVD_RESP,
            self.pydevd_payload(*args, **kwargs),
            reqid=self.PYDEVD_CMD,
        )

    def pydevd_payload(self, *args, **kwargs):
        return ''

    def send_request(self, **args):
        self.req = self.fix.send_request(self.COMMAND, args)
        return self.req

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
    PYDEVD_RESP = CMD_RETURN

    def pydevd_payload(self, *threads):
        return self.debugger_msgs.format_threads(*threads)

    def test_few(self):
        with self.launched(default_threads=False):
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

    def test_none(self):
        with self.launched(default_threads=False):
            self.set_debugger_response()
            self.send_request()
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_response(
                threads=[],
            ),
            # no events
        ])
        self.assert_received(self.debugger, [
            self.expected_pydevd_request(),
        ])


class StackTraceTests(NormalRequestTest, unittest.TestCase):

    COMMAND = 'stackTrace'

    def test_basic(self):
        thread = (10, 'x')
        with self.launched():
            with self.hidden():
                tid = self.set_thread(thread)
                self.suspend(thread, CMD_THREAD_SUSPEND, *[
                    # (pfid, func, file, line)
                    (2, 'spam', 'abc.py', 10),
                    (5, 'eggs', 'xyz.py', 2),
                ])
            self.send_request(
                threadId=tid,
                #startFrame=1,
                #levels=1,
            )
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_response(
                stackFrames=[
                    {
                        'id': 1,
                        'name': 'spam',
                        'source': {'path': 'abc.py'},
                        'line': 10,
                        'column': 0,
                    },
                    {
                        'id': 2,
                        'name': 'eggs',
                        'source': {'path': 'xyz.py'},
                        'line': 2,
                        'column': 0,
                    },
                ],
                totalFrames=2,
            ),
            # no events
        ])
        self.assert_received(self.debugger, [])

    def test_no_threads(self):
        with self.launched():
            req = self.send_request(
                threadId=10,
            )
            received = self.vsc.received

        self.assert_vsc_failure(received, [], req)
        self.assert_received(self.debugger, [])

    def test_unknown_thread(self):
        thread = (10, 'x')
        with self.launched():
            with self.hidden():
                tid = self.set_threads(thread)[thread]
            req = self.send_request(
                threadId=tid + 1,
            )
            received = self.vsc.received

        self.assert_vsc_failure(received, [], req)
        self.assert_received(self.debugger, [])


class ScopesTests(NormalRequestTest, unittest.TestCase):

    COMMAND = 'scopes'

    def test_basic(self):
        thread = (10, 'x')
        with self.launched():
            with self.hidden():
                self.pause(thread, *[
                    # (pfid, func, file, line)
                    (2, 'spam', 'abc.py', 10),  # VSC frame ID 1
                    (5, 'eggs', 'xyz.py', 2),  # VSC frame ID 2
                ])
            self.send_request(
                frameId=1,
            )
            received = self.vsc.received
        self.assert_vsc_received(received, [
            self.expected_response(
                scopes=[{
                    'name': 'Locals',
                    'expensive': False,
                    'variablesReference': 1,  # matches frame 2 locals
                }],
            ),
            # no events
        ])
        self.assert_received(self.debugger, [])


class VariablesTests(NormalRequestTest, unittest.TestCase):

    COMMAND = 'variables'
    PYDEVD_CMD = [
        CMD_GET_FRAME,
        CMD_GET_VARIABLE,
    ]

    def pydevd_payload(self, *variables):
        return self.debugger_msgs.format_variables(*variables)

    def test_locals(self):
        class MyType(object):
            pass
        obj = MyType()
        thread = (10, 'x')
        self.PYDEVD_CMD = CMD_GET_FRAME
        with self.launched():
            with self.hidden():
                self.pause(thread, *[
                    # (pfid, func, file, line)
                    (2, 'spam', 'abc.py', 10),  # VSC frame ID 1
                    (5, 'eggs', 'xyz.py', 2),  # VSC frame ID 2
                ])
            self.set_debugger_response(
                # (var, value, iscontainer)
                ('spam', 'eggs', False),
                ('ham', [1, 2, 3], True),
                ('x', True, False),
                ('y', 42, False),
                ('z', obj, False),
            )
            self.send_request(
                variablesReference=1,  # matches frame locals
            )
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_response(
                variables=[
                    {
                        'name': 'spam',
                        'type': str(str),
                        'value': 'eggs',
                    },
                    {
                        'name': 'ham',
                        'type': str(list),
                        'value': '[1, 2, 3]',
                        'variablesReference': 2,
                    },
                    {
                        'name': 'x',
                        'type': str(bool),
                        'value': 'True',
                    },
                    {
                        'name': 'y',
                        'type': str(int),
                        'value': '42',
                    },
                    {
                        'name': 'z',
                        'type': str(MyType),
                        'value': str(obj),
                    },
                ],
            ),
            # no events
        ])
        self.assert_received(self.debugger, [
            self.expected_pydevd_request('10\t2\tFRAME'),
        ])

    def test_container(self):
        thread = (10, 'x')
        self.PYDEVD_CMD = CMD_GET_FRAME
        with self.launched():
            with self.hidden():
                self.pause(thread, *[
                    # (pfid, func, file, line)
                    (2, 'spam', 'abc.py', 10),  # VSC frame ID 1
                    (5, 'eggs', 'xyz.py', 2),  # VSC frame ID 2
                ])
                self.set_debugger_response(
                    # (var, value, iscontainer)
                    ('spam', {'x', 'y', 'z'}, True),
                )
                self.send_request(
                    variablesReference=1,  # matches frame locals
                )
            self.PYDEVD_CMD = CMD_GET_VARIABLE
            self.set_debugger_response(
                # (var, value, iscontainer)
                ('x', 1, False),
                ('y', 2, False),
                ('z', 3, False),
            )
            self.send_request(
                variablesReference=2,  # matches container
            )
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_response(
                variables=[
                    {
                        'name': 'x',
                        'type': str(int),
                        'value': '1',
                    },
                    {
                        'name': 'y',
                        'type': str(int),
                        'value': '2',
                    },
                    {
                        'name': 'z',
                        'type': str(int),
                        'value': '3',
                    },
                ],
            ),
            # no events
        ])
        self.assert_received(self.debugger, [
            self.expected_pydevd_request('10\t2\tFRAME\tspam'),
        ])


# TODO: finish!
@unittest.skip('not finished')
class SetVariableTests(NormalRequestTest, unittest.TestCase):

    COMMAND = 'setVariable'
    PYDEVD_CMD = CMD_CHANGE_VARIABLE
    PYDEVD_RESP = CMD_RETURN

    def test_basic(self):
        raise NotImplementedError
        with self.launched():
            self.set_debugger_response(
                # ...
            )
            self.send_request(
                # ...
            )
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_response(
                # ...
            ),
            # no events
        ])
        self.assert_received(self.debugger, [
            self.expected_pydevd_request(),
        ])


# TODO: finish!
@unittest.skip('not finished')
class EvaluateTests(NormalRequestTest, unittest.TestCase):

    COMMAND = 'evaluate'
    PYDEVD_CMD = CMD_EVALUATE_EXPRESSION

    def test_basic(self):
        raise NotImplementedError
        with self.launched():
            self.set_debugger_response(
                # ...
            )
            self.send_request(
                # ...
            )
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_response(
                # ...
            ),
            # no events
        ])
        self.assert_received(self.debugger, [
            self.expected_pydevd_request(),
        ])


# TODO: finish!
@unittest.skip('not finished')
class PauseTests(NormalRequestTest, unittest.TestCase):

    COMMAND = 'pause'
    PYDEVD_CMD = CMD_THREAD_SUSPEND
    PYDEVD_RESP = None

    def test_basic(self):
        raise NotImplementedError
        with self.launched():
            self.send_request(
                # ...
            )
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_response(
                # ...
            ),
            # no events
        ])
        self.assert_received(self.debugger, [
            self.expected_pydevd_request(),
        ])


# TODO: finish!
@unittest.skip('not finished')
class ContinueTests(NormalRequestTest, unittest.TestCase):

    COMMAND = 'continue'
    PYDEVD_CMD = CMD_THREAD_RUN
    PYDEVD_RESP = None

    def test_basic(self):
        raise NotImplementedError
        with self.launched():
            self.send_request(
                # ...
            )
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_response(
                # ...
            ),
            # no events
        ])
        self.assert_received(self.debugger, [
            self.expected_pydevd_request(),
        ])


# TODO: finish!
@unittest.skip('not finished')
class NextTests(NormalRequestTest, unittest.TestCase):

    COMMAND = 'next'
    PYDEVD_CMD = CMD_STEP_OVER
    PYDEVD_RESP = None

    def test_basic(self):
        raise NotImplementedError
        with self.launched():
            self.send_request(
                # ...
            )
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_response(
                # ...
            ),
            # no events
        ])
        self.assert_received(self.debugger, [
            self.expected_pydevd_request(),
        ])


# TODO: finish!
@unittest.skip('not finished')
class StepInTests(NormalRequestTest, unittest.TestCase):

    COMMAND = 'stepIn'
    PYDEVD_CMD = CMD_STEP_INTO
    PYDEVD_RESP = None

    def test_basic(self):
        raise NotImplementedError
        with self.launched():
            self.send_request(
                # ...
            )
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_response(
                # ...
            ),
            # no events
        ])
        self.assert_received(self.debugger, [
            self.expected_pydevd_request(),
        ])


# TODO: finish!
@unittest.skip('not finished')
class StepOutTests(NormalRequestTest, unittest.TestCase):

    COMMAND = 'stepOut'
    PYDEVD_CMD = CMD_STEP_RETURN
    PYDEVD_RESP = None

    def test_basic(self):
        raise NotImplementedError
        with self.launched():
            self.send_request(
                # ...
            )
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_response(
                # ...
            ),
            # no events
        ])
        self.assert_received(self.debugger, [
            self.expected_pydevd_request(),
        ])


# TODO: finish!
@unittest.skip('not finished')
class SetBreakpointsTests(NormalRequestTest, unittest.TestCase):

    COMMAND = 'setBreakpoints'
    PYDEVD_CMD = [
        [CMD_REMOVE_BREAK],
        [CMD_SET_BREAK],
    ]
    PYDEVD_RESP = None

    def test_basic(self):
        raise NotImplementedError
        with self.launched():
            self.send_request(
                # ...
            )
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_response(
                # ...
            ),
            # no events
        ])
        self.assert_received(self.debugger, [
            self.expected_pydevd_request(),
        ])


# TODO: finish!
@unittest.skip('not finished')
class SetExceptionBreakpointsTests(NormalRequestTest, unittest.TestCase):

    COMMAND = 'setExceptionBreakpoints'
    PYDEVD_CMD = [
        [CMD_REMOVE_EXCEPTION_BREAK],
        [CMD_ADD_EXCEPTION_BREAK],
    ]
    PYDEVD_RESP = None

    def test_basic(self):
        raise NotImplementedError
        with self.launched():
            self.send_request(
                # ...
            )
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_response(
                # ...
            ),
            # no events
        ])
        self.assert_received(self.debugger, [
            self.expected_pydevd_request(),
        ])


# TODO: finish!
@unittest.skip('not finished')
class ExceptionInfoTests(NormalRequestTest, unittest.TestCase):

    COMMAND = 'exceptionInfo'

    def test_basic(self):
        raise NotImplementedError
        with self.launched():
            self.send_request(
                # ...
            )
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_response(
                # ...
            ),
            # no events
        ])
        self.assert_received(self.debugger, [])


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
