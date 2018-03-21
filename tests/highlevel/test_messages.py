import os
import sys
import unittest

from _pydevd_bundle.pydevd_comm import (
    CMD_ADD_EXCEPTION_BREAK,
    CMD_CHANGE_VARIABLE,
    CMD_EVALUATE_EXPRESSION,
    CMD_EXEC_EXPRESSION,
    CMD_EXIT,
    CMD_GET_BREAKPOINT_EXCEPTION,
    CMD_GET_FRAME,
    CMD_GET_VARIABLE,
    CMD_LIST_THREADS,
    CMD_PROCESS_CREATED,
    CMD_REMOVE_BREAK,
    CMD_REMOVE_EXCEPTION_BREAK,
    CMD_RETURN,
    CMD_SEND_CURR_EXCEPTION_TRACE,
    CMD_SEND_CURR_EXCEPTION_TRACE_PROCEEDED,
    CMD_SET_BREAK,
    CMD_SHOW_CONSOLE,
    CMD_STEP_CAUGHT_EXCEPTION,
    CMD_STEP_INTO,
    CMD_STEP_OVER,
    CMD_STEP_RETURN,
    CMD_THREAD_CREATE,
    CMD_THREAD_KILL,
    CMD_THREAD_RUN,
    CMD_THREAD_SUSPEND,
    CMD_VERSION,
    CMD_WRITE_TO_CONSOLE,
)

from . import OS_ID, RunningTest
from ptvsd.wrapper import UnsupportedPyDevdCommandError


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
                supportsEvaluateForHovers=True,
                supportsSetExpression=True,
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
        req = self.fix.send_request(self.COMMAND, args)
        if not self.ishidden:
            try:
                reqs = self.reqs
            except AttributeError:
                reqs = self.reqs = []
            reqs.append(req)
        return req

    def _next_request(self):
        return self.reqs.pop(0)

    def expected_response(self, **body):
        return self.new_response(
            self._next_request(),
            **body
        )

    def expected_failure(self, err, **body):
        return self.new_failure(
            self._next_request(),
            err,
            seq=None,
            **body
        )

    def expected_pydevd_request(self, *args):
        return self.debugger_msgs.new_request(self.PYDEVD_CMD, *args)


class RestartTests(NormalRequestTest, unittest.TestCase):

    COMMAND = 'restart'

    def test_unsupported(self):
        with self.launched():
            self.send_request()
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_failure('Unknown command'),
        ])
        self.assert_received(self.debugger, [])


class ThreadsTests(NormalRequestTest, unittest.TestCase):

    COMMAND = 'threads'
    PYDEVD_CMD = CMD_LIST_THREADS
    PYDEVD_RESP = CMD_RETURN

    def pydevd_payload(self, *threads):
        return self.debugger_msgs.format_threads(*threads)

    def test_few(self):
        with self.launched(default_threads=False):
            self.set_debugger_response(
                (1, 'MainThread'),
                (10, 'spam'),
                (11, 'pydevd.eggs'),
                (12, 'Thread-12'),
            )
            self.send_request()
            received = self.vsc.received

        self.assert_vsc_received(received, [
            # MainThread is #1.
            self.new_event('thread', threadId=2, reason='started'),
            self.new_event('thread', threadId=3, reason='started'),
            self.expected_response(
                threads=[
                    {'id': 1, 'name': 'MainThread'},
                    {'id': 2, 'name': 'spam'},
                    # Threads named 'pydevd.*' are ignored.
                    {'id': 3, 'name': 'Thread-12'},
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
        with self.launched():
            with self.hidden():
                tid, thread = self.set_thread('x')
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
                        'column': 1,
                    },
                    {
                        'id': 2,
                        'name': 'eggs',
                        'source': {'path': 'xyz.py'},
                        'line': 2,
                        'column': 1,
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
        with self.launched():
            with self.hidden():
                tid, _ = self.set_thread('x')
            req = self.send_request(
                threadId=tid + 1,
            )
            received = self.vsc.received

        self.assert_vsc_failure(received, [], req)
        self.assert_received(self.debugger, [])


class ScopesTests(NormalRequestTest, unittest.TestCase):

    COMMAND = 'scopes'

    def test_basic(self):
        with self.launched():
            with self.hidden():
                self.pause('x', *[
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
        self.PYDEVD_CMD = CMD_GET_FRAME
        with self.launched():
            with self.hidden():
                _, thread = self.pause('t', *[
                    # (pfid, func, file, line)
                    (2, 'spam', 'abc.py', 10),  # VSC frame ID 1
                    (5, 'eggs', 'xyz.py', 2),  # VSC frame ID 2
                ])
            self.set_debugger_response(
                # (var, value)
                ('spam', 'eggs'),
                ('ham', [1, 2, 3]),
                ('x', True),
                ('y', 42),
                ('z', obj),
            )
            self.send_request(
                variablesReference=1,  # matches frame locals
            )
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_response(
                variables=[
                    {
                        'name': 'ham',
                        'type': 'list',
                        'value': '[1, 2, 3]',
                        'variablesReference': 2,
                    },
                    {
                        'name': 'spam',
                        'type': 'str',
                        'value': "'eggs'",
                        'presentationHint': {
                            'attributes': ['rawString'],
                        },
                    },
                    {
                        'name': 'x',
                        'type': 'bool',
                        'value': 'True',
                    },
                    {
                        'name': 'y',
                        'type': 'int',
                        'value': '42',
                    },
                    {
                        'name': 'z',
                        'type': 'MyType',
                        'variablesReference': 3,
                        'value': str(obj),
                    },
                ],
            ),
            # no events
        ])
        self.assert_received(self.debugger, [
            self.expected_pydevd_request('{}\t2\tFRAME'.format(thread.id)),
        ])

    def test_container(self):
        self.PYDEVD_CMD = CMD_GET_FRAME
        with self.launched():
            with self.hidden():
                _, thread = self.pause('t', *[
                    # (pfid, func, file, line)
                    (2, 'spam', 'abc.py', 10),  # VSC frame ID 1
                    (5, 'eggs', 'xyz.py', 2),  # VSC frame ID 2
                ])
                self.set_debugger_response(
                    # (var, value)
                    ('spam', {'x', 'y', 'z'}),
                )
                self.send_request(
                    variablesReference=1,  # matches frame locals
                )
            self.PYDEVD_CMD = CMD_GET_VARIABLE
            self.set_debugger_response(
                # (var, value)
                ('x', 1),
                ('y', 2),
                ('z', 3),
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
                        'type': 'int',
                        'value': '1',
                        'evaluateName': 'spam.x',
                    },
                    {
                        'name': 'y',
                        'type': 'int',
                        'value': '2',
                        'evaluateName': 'spam.y',
                    },
                    {
                        'name': 'z',
                        'type': 'int',
                        'value': '3',
                        'evaluateName': 'spam.z',
                    },
                ],
            ),
            # no events
        ])
        self.assert_received(self.debugger, [
            self.expected_pydevd_request(
                '{}\t2\tFRAME\tspam'.format(thread.id)),
        ])


class SetVariableTests(NormalRequestTest, unittest.TestCase):

    COMMAND = 'setVariable'
    PYDEVD_CMD = CMD_CHANGE_VARIABLE
    PYDEVD_RESP = CMD_RETURN

    def pydevd_payload(self, variable):
        return self.debugger_msgs.format_variables(variable)

    def _set_variables(self, varref, *variables):
        with self.hidden():
            self.fix.set_debugger_response(
                CMD_GET_FRAME,
                self.debugger_msgs.format_variables(*variables),
            )
            self.fix.send_request('variables', dict(
                variablesReference=varref,
            ))

    def test_local(self):
        with self.launched():
            with self.hidden():
                _, thread = self.pause('t', *[
                    # (pfid, func, file, line)
                    (2, 'spam', 'abc.py', 10),  # VSC frame ID 1
                    (5, 'eggs', 'xyz.py', 2),  # VSC frame ID 2
                ])
                self._set_variables(
                    1,  # matches frame locals
                    ('spam', 42),
                )
            self.PYDEVD_CMD = CMD_EXEC_EXPRESSION
            self.PYDEVD_RESP = CMD_EVALUATE_EXPRESSION
            expected = self.expected_pydevd_request(
                '{}\t2\tLOCAL\tspam = eggs\t1'.format(thread.id))
            self.set_debugger_response(
                ('spam', 'eggs'),
            )
            self.PYDEVD_CMD = CMD_EVALUATE_EXPRESSION
            self.set_debugger_response(
                ('spam', 'eggs'),
            )
            self.send_request(
                variablesReference=1,  # matches frame locals
                name='spam',
                value='eggs',
            )
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_response(
                type='str',
                value="'eggs'",
            ),
            # no events
        ])
        self.assert_received(self.debugger, [
            expected,
            self.expected_pydevd_request(
                '{}\t2\tLOCAL\tspam\t1'.format(thread.id)),
        ])

    def test_container(self):
        with self.launched():
            with self.hidden():
                _, thread = self.pause('t', *[
                    # (pfid, func, file, line)
                    (2, 'spam', 'abc.py', 10),  # VSC frame ID 1
                    (5, 'eggs', 'xyz.py', 2),  # VSC frame ID 2
                ])
                self._set_variables(
                    1,  # matches frame locals
                    ('spam', {'x': 1}),
                )
            self.PYDEVD_CMD = CMD_EXEC_EXPRESSION
            self.PYDEVD_RESP = CMD_EVALUATE_EXPRESSION
            expected = self.expected_pydevd_request(
                '{}\t2\tLOCAL\tspam.x = 2\t1'.format(thread.id))
            self.set_debugger_response(
                ('x', 2),
            )
            self.PYDEVD_CMD = CMD_EVALUATE_EXPRESSION
            self.set_debugger_response(
                ('x', 2),
            )
            self.send_request(
                variablesReference=2,  # matches spam
                name='x',
                value='2',
            )
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_response(
                type='int',
                value='2',
            ),
            # no events
        ])
        self.assert_received(self.debugger, [
            expected,
            self.expected_pydevd_request(
                '{}\t2\tLOCAL\tspam.x\t1'.format(thread.id)),
        ])


class EvaluateTests(NormalRequestTest, unittest.TestCase):

    COMMAND = 'evaluate'
    PYDEVD_CMD = CMD_EVALUATE_EXPRESSION

    def pydevd_payload(self, variable):
        return self.debugger_msgs.format_variables(variable)

    def test_basic(self):
        with self.launched():
            with self.hidden():
                _, thread = self.pause('x', *[
                    # (pfid, func, file, line)
                    (2, 'spam', 'abc.py', 10),  # VSC frame ID 1
                    (5, 'eggs', 'xyz.py', 2),  # VSC frame ID 2
                ])
            self.set_debugger_response(
                ('spam + 1', 43),
            )
            self.send_request(
                frameId=2,
                expression='spam + 1',
                context=None,
            )
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_response(
                type='int',
                result='43',
            ),
            # no events
        ])
        self.assert_received(self.debugger, [
            self.expected_pydevd_request(
                '{}\t5\tLOCAL\tspam + 1\t1'.format(thread.id)),
        ])

    def test_hover(self):
        with self.launched():
            with self.hidden():
                _, thread = self.pause('x', *[
                    # (pfid, func, file, line)
                    (2, 'spam', 'abc.py', 10),  # VSC frame ID 1
                    (5, 'eggs', 'xyz.py', 2),  # VSC frame ID 2
                ])
            self.set_debugger_response(
                ('spam + 1', 'err:43'),
            )
            self.send_request(
                frameId=2,
                expression='spam + 1',
                context='hover',
            )
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_response(
                result=None,
                variablesReference=0,
            ),
            # no events
        ])
        self.assert_received(self.debugger, [
            self.expected_pydevd_request(
                '{}\t5\tLOCAL\tspam + 1\t1'.format(thread.id)),
        ])


class PauseTests(NormalRequestTest, unittest.TestCase):

    COMMAND = 'pause'
    PYDEVD_CMD = CMD_THREAD_SUSPEND
    PYDEVD_RESP = None

    def test_pause_one(self):
        with self.launched():
            with self.hidden():
                threads = self.set_threads('spam', 'eggs')
            tid, thread = threads[0]
            self.send_request(
                threadId=tid,
            )
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_response(),
            # no events
        ])
        self.assert_received(self.debugger, [
            self.expected_pydevd_request(str(thread.id)),
        ])

    # TODO: finish!
    @unittest.skip('not finished')
    def test_pause_all(self):
        raise NotImplementedError


class ContinueTests(NormalRequestTest, unittest.TestCase):

    COMMAND = 'continue'
    PYDEVD_CMD = CMD_THREAD_RUN
    PYDEVD_RESP = None

    def test_basic(self):
        with self.launched():
            with self.hidden():
                tid, thread = self.pause('x', *[
                    (2, 'spam', 'abc.py', 10),
                ])
            self.send_request(
                threadId=tid,
            )
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_response(),
            # no events
        ])
        self.assert_received(self.debugger, [
            self.expected_pydevd_request(str(thread.id)),
        ])


class NextTests(NormalRequestTest, unittest.TestCase):

    COMMAND = 'next'
    PYDEVD_CMD = CMD_STEP_OVER
    PYDEVD_RESP = None

    def test_basic(self):
        with self.launched():
            with self.hidden():
                tid, thread = self.pause('x', *[
                    (2, 'spam', 'abc.py', 10),
                ])
            self.send_request(
                threadId=tid,
            )
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_response(),
            # no events
        ])
        self.assert_received(self.debugger, [
            self.expected_pydevd_request(str(thread.id)),
        ])


class StepInTests(NormalRequestTest, unittest.TestCase):

    COMMAND = 'stepIn'
    PYDEVD_CMD = CMD_STEP_INTO
    PYDEVD_RESP = None

    def test_basic(self):
        with self.launched():
            with self.hidden():
                tid, thread = self.pause('x', *[
                    (2, 'spam', 'abc.py', 10),
                ])
            self.send_request(
                threadId=tid,
            )
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_response(),
            # no events
        ])
        self.assert_received(self.debugger, [
            self.expected_pydevd_request(str(thread.id)),
        ])


class StepOutTests(NormalRequestTest, unittest.TestCase):

    COMMAND = 'stepOut'
    PYDEVD_CMD = CMD_STEP_RETURN
    PYDEVD_RESP = None

    def test_basic(self):
        with self.launched():
            with self.hidden():
                tid, thread = self.pause('x', *[
                    (2, 'spam', 'abc.py', 10),
                ])
            self.send_request(
                threadId=tid,
            )
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_response(),
            # no events
        ])
        self.assert_received(self.debugger, [
            self.expected_pydevd_request(str(thread.id)),
        ])


class StepBackTests(NormalRequestTest, unittest.TestCase):

    COMMAND = 'stepBack'

    def test_unsupported(self):
        with self.launched():
            self.send_request(
                threadId=10,
            )
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_failure('Unknown command'),
        ])
        self.assert_received(self.debugger, [])


class ReverseContinueTests(NormalRequestTest, unittest.TestCase):

    COMMAND = 'reverseContinue'

    def test_unsupported(self):
        with self.launched():
            self.send_request(
                threadId=10,
            )
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_failure('Unknown command'),
        ])
        self.assert_received(self.debugger, [])


class RestartFrameTests(NormalRequestTest, unittest.TestCase):

    COMMAND = 'restartFrame'

    def test_unsupported(self):
        with self.launched():
            self.send_request(
                threadId=10,
            )
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_failure('Unknown command'),
        ])
        self.assert_received(self.debugger, [])


class GotoTests(NormalRequestTest, unittest.TestCase):

    COMMAND = 'goto'

    def test_unsupported(self):
        with self.launched():
            self.send_request(
                threadId=10,
                targetId=1,
            )
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_failure('Unknown command'),
        ])
        self.assert_received(self.debugger, [])


class SetBreakpointsTests(NormalRequestTest, unittest.TestCase):

    COMMAND = 'setBreakpoints'
    PYDEVD_CMD = [
        [CMD_REMOVE_BREAK],
        [CMD_SET_BREAK],
    ]
    PYDEVD_RESP = None

    def test_initial(self):
        with self.launched():
            self.send_request(
                source={'path': 'spam.py'},
                breakpoints=[
                    {'line': '10'},
                    {'line': '15',
                     'condition': 'i == 3'},
                ],
            )
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_response(
                breakpoints=[
                    {'id': 1,
                     'verified': True,
                     'line': '10'},
                    {'id': 2,
                     'verified': True,
                     'line': '15'},
                ],
            ),
            # no events
        ])
        self.PYDEVD_CMD = CMD_SET_BREAK
        self.assert_received(self.debugger, [
            self.expected_pydevd_request(
                '1\tpython-line\tspam.py\t10\tNone\tNone\tNone'),
            self.expected_pydevd_request(
                '2\tpython-line\tspam.py\t15\tNone\ti == 3\tNone'),
        ])

    def test_with_existing(self):
        with self.launched():
            with self.hidden():
                self.PYDEVD_CMD = CMD_SET_BREAK
                self.expected_pydevd_request(
                    '1\tpython-line\tspam.py\t10\tNone\tNone\tNone')
                self.expected_pydevd_request(
                    '2\tpython-line\tspam.py\t17\tNone\tNone\tNone')
                self.fix.send_request('setBreakpoints', dict(
                    source={'path': 'spam.py'},
                    breakpoints=[
                        {'line': '10'},
                        {'line': '17'},
                    ],
                ))
            self.send_request(
                source={'path': 'spam.py'},
                breakpoints=[
                    {'line': '113'},
                    {'line': '2'},
                    {'line': '10'},  # a repeat
                ],
            )
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_response(
                breakpoints=[
                    {'id': 3,
                     'verified': True,
                     'line': '113'},
                    {'id': 4,
                     'verified': True,
                     'line': '2'},
                    {'id': 5,
                     'verified': True,
                     'line': '10'},
                ],
            ),
            # no events
        ])
        self.PYDEVD_CMD = CMD_REMOVE_BREAK
        if self.debugger.received[0].payload.endswith('1'):
            removed = [
                self.expected_pydevd_request('python-line\tspam.py\t1'),
                self.expected_pydevd_request('python-line\tspam.py\t2'),
            ]
        else:
            removed = [
                self.expected_pydevd_request('python-line\tspam.py\t2'),
                self.expected_pydevd_request('python-line\tspam.py\t1'),
            ]
        self.PYDEVD_CMD = CMD_SET_BREAK
        self.assert_received(self.debugger, removed + [
            self.expected_pydevd_request(
                '3\tpython-line\tspam.py\t113\tNone\tNone\tNone'),
            self.expected_pydevd_request(
                '4\tpython-line\tspam.py\t2\tNone\tNone\tNone'),
            self.expected_pydevd_request(
                '5\tpython-line\tspam.py\t10\tNone\tNone\tNone'),
        ])

    # TODO: fix!
    @unittest.skip('broken: https://github.com/Microsoft/ptvsd/issues/126')
    def test_multiple_files(self):
        with self.launched():
            self.send_request(
                source={'path': 'spam.py'},
                breakpoints=[{'line': '10'}],
            )
            self.send_request(
                source={'path': 'eggs.py'},
                breakpoints=[{'line': '17'}],
            )
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_response(
                breakpoints=[
                    {'id': 1,
                     'verified': True,
                     'line': '10'},
                ],
            ),
            self.expected_response(
                breakpoints=[
                    {'id': 2,
                     'verified': True,
                     'line': '17'},
                ],
            ),
            # no events
        ])

        self.PYDEVD_CMD = CMD_SET_BREAK
        self.assert_received(self.debugger, [
            self.expected_pydevd_request(
                '1\tpython-line\tspam.py\t10\tNone\tNone\tNone'),
            self.expected_pydevd_request(
                '2\tpython-line\teggs.py\t17\tNone\tNone\tNone'),
        ])


class SetFunctionBreakpointsTests(NormalRequestTest, unittest.TestCase):

    COMMAND = 'setFunctionBreakpoints'

    def test_unsupported(self):
        with self.launched():
            self.send_request(
                breakpoints=[
                    {
                        'name': 'spam',
                    },
                ],
            )
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_failure('Unknown command'),
        ])
        self.assert_received(self.debugger, [])


class SetExceptionBreakpointsTests(NormalRequestTest, unittest.TestCase):

    COMMAND = 'setExceptionBreakpoints'
    PYDEVD_CMD = [
        [CMD_REMOVE_EXCEPTION_BREAK],
        [CMD_ADD_EXCEPTION_BREAK],
    ]
    PYDEVD_RESP = None

    def _check_options(self, options, expectedpydevd):
        with self.launched():
            self.send_request(
                filters=[],
                exceptionOptions=options,
            )
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_response(),
        ])
        self.PYDEVD_CMD = CMD_ADD_EXCEPTION_BREAK
        self.assert_received(
            self.debugger,
            [self.expected_pydevd_request(expect)
             for expect in expectedpydevd],
        )

    def _check_option(self, paths, mode, expectedpydevd):
        options = [{
            'path': paths,
            'breakMode': mode,
        }]
        self._check_options(options, expectedpydevd)

    # TODO: We've hard-coded the currently supported modes.  If other
    # modes are added later then we need to add more tests.  We don't
    # have a programatic alternative that is very readable.

    def test_single_option_single_path_mode_never(self):
        path = {
            'names': ['Python Exceptions'],
        }
        self._check_option(
            [path],
            'never',
            ['python-BaseException\t0\t0\t0'],
        )

    def test_single_option_single_path_mode_always(self):
        path = {
            'names': ['Python Exceptions'],
        }
        self._check_option(
            [path],
            'always',
            ['python-BaseException\t3\t0\t0'],
        )

    def test_single_option_single_path_mode_unhandled(self):
        path = {
            'names': ['Python Exceptions'],
        }
        self._check_option(
            [path],
            'unhandled',
            ['python-BaseException\t0\t1\t0'],
        )

    def test_single_option_single_path_mode_userUnhandled(self):
        path = {
            'names': ['Python Exceptions'],
        }
        self._check_option(
            [path],
            'userUnhandled',
            ['python-BaseException\t0\t1\t0'],
        )

    def test_single_option_empty_paths(self):
        self._check_option([], 'userUnhandled', [])

    def test_single_option_single_path_python_exception(self):
        path = {
            'names': ['ImportError'],
        }
        self._check_option(
            [path],
            'userUnhandled',
            [],
        )

    def test_single_option_single_path_not_python_category(self):
        path = {
            'names': ['not Python Exceptions'],
        }
        self._check_option(
            [path],
            'userUnhandled',
            [],
        )

    # TODO: verify behavior
    @unittest.skip('poorly specified')
    def test_single_option_single_path_multiple_names(self):
        path = {
            'names': [
                'Python Exceptions',
                # The rest are ignored by ptvsd?  VSC?
                'spam',
                'eggs'
            ],
        }
        self._check_option(
            [path],
            'always',
            ['python-BaseException\t3\t0\t0'],
        )

    def test_single_option_shallow_path(self):
        path = [
            {'names': ['Python Exceptions']},
            {'names': ['ImportError']},
        ]
        self._check_option(path, 'always', [
            'python-ImportError\t3\t0\t0',
        ])

    def test_single_option_deep_path(self):
        path = [
            {'names': ['Python Exceptions']},
            {'names': ['ImportError']},
            {'names': ['RuntimeError']},
            {'names': ['ValueError']},
            {'names': ['MyError']},
        ]
        self._check_option(path, 'always', [
            'python-ImportError\t3\t0\t0',
            'python-RuntimeError\t3\t0\t0',
            'python-ValueError\t3\t0\t0',
            'python-MyError\t3\t0\t0',
        ])

    # TODO: verify behavior
    @unittest.skip('poorly specified')
    def test_single_option_multiple_names(self):
        path = [
            {'names': ['Python Exceptions']},
            {'names': ['ImportError', 'RuntimeError', 'ValueError']},
        ]
        self._check_option(path, 'always', [
            'python-ImportError\t3\t0\t0',
            'python-RuntimeError\t3\t0\t0',
            'python-ValueError\t3\t0\t0',
        ])

    # TODO: verify behavior
    @unittest.skip('poorly specified')
    def test_single_option_first_path_not_category(self):
        self._check_option(
            [
                {'names': ['not Python Exceptions']},
                {'names': ['other']},
             ],
            'always',
            [],
        )

    # TODO: verify behavior
    @unittest.skip('poorly specified')
    def test_single_option_unknown_exception(self):
        path = [
            {'names': ['Python Exceptions']},
            {'names': ['AnUnknownException']},
        ]
        with self.assertRaises(ValueError):
            self._check_option(path, 'always', [])

    def test_multiple_options(self):
        options = [
            # shallow path
            {'path': [
                {'names': ['Python Exceptions']},
                {'names': ['ImportError']},
             ],
             'breakMode': 'always'},
            # ignored
            {'path': [
                {'names': ['non-Python Exceptions']},
                {'names': ['OSError']},
             ],
             'breakMode': 'always'},
            # deep path
            {'path': [
                {'names': ['Python Exceptions']},
                {'names': ['ModuleNotFoundError']},
                {'names': ['RuntimeError']},
                {'names': ['MyError']},
             ],
             'breakMode': 'unhandled'},
            # multiple names
            {'path': [
                {'names': ['Python Exceptions']},
                {'names': ['ValueError', 'IndexError']},
             ],
             'breakMode': 'never'},
            # catch-all
            {'path': [
                {'names': ['Python Exceptions']},
             ],
             'breakMode': 'userUnhandled'},
        ]
        self._check_options(options, [
            # shallow path
            'python-ImportError\t3\t0\t0',
            # ignored
            # deep path
            'python-ModuleNotFoundError\t0\t1\t0',
            'python-RuntimeError\t0\t1\t0',
            'python-MyError\t0\t1\t0',
            # multiple names
            'python-ValueError\t0\t0\t0',
            'python-IndexError\t0\t0\t0',
            # catch-all
            'python-BaseException\t0\t1\t0',
        ])

    def test_options_with_existing_filters(self):
        with self.launched():
            with self.hidden():
                self.PYDEVD_CMD = CMD_ADD_EXCEPTION_BREAK
                self.expected_pydevd_request('python-BaseException\t0\t1\t0')
                self.fix.send_request('setExceptionBreakpoints', dict(
                    filters=[
                        'uncaught',
                    ],
                ))
            self.send_request(
                filters=[],
                exceptionOptions=[
                    {'path': [
                        {'names': ['Python Exceptions']},
                        {'names': ['ImportError']},
                     ],
                     'breakMode': 'never'},
                    {'path': [
                        {'names': ['Python Exceptions']},
                        {'names': ['RuntimeError']},
                     ],
                     'breakMode': 'always'},
                ]
            )
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_response(),
        ])
        self.PYDEVD_CMD = CMD_REMOVE_EXCEPTION_BREAK
        removed = [
            self.expected_pydevd_request('python-BaseException'),
        ]
        self.PYDEVD_CMD = CMD_ADD_EXCEPTION_BREAK
        self.assert_received(self.debugger, removed + [
            self.expected_pydevd_request('python-ImportError\t0\t0\t0'),
            self.expected_pydevd_request('python-RuntimeError\t3\t0\t0'),
        ])

    def test_options_with_existing_options(self):
        with self.launched():
            with self.hidden():
                self.PYDEVD_CMD = CMD_ADD_EXCEPTION_BREAK
                self.expected_pydevd_request('python-ImportError\t0\t1\t0')
                self.expected_pydevd_request('python-BaseException\t3\t0\t0')
                self.fix.send_request('setExceptionBreakpoints', dict(
                    filters=[],
                    exceptionOptions=[
                        {'path': [
                            {'names': ['Python Exceptions']},
                            {'names': ['ImportError']},
                         ],
                         'breakMode': 'unhandled'},
                        {'path': [
                            {'names': ['Python Exceptions']},
                         ],
                         'breakMode': 'always'},
                    ],
                ))
            self.send_request(
                filters=[],
                exceptionOptions=[
                    {'path': [
                        {'names': ['Python Exceptions']},
                        {'names': ['ImportError']},
                     ],
                     'breakMode': 'never'},
                    {'path': [
                        {'names': ['Python Exceptions']},
                        {'names': ['RuntimeError']},
                     ],
                     'breakMode': 'unhandled'},
                ]
            )
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_response(),
        ])
        self.PYDEVD_CMD = CMD_REMOVE_EXCEPTION_BREAK
        if self.debugger.received[0].payload == 'python-ImportError':
            removed = [
                self.expected_pydevd_request('python-ImportError'),
                self.expected_pydevd_request('python-BaseException'),
            ]
        else:
            removed = [
                self.expected_pydevd_request('python-BaseException'),
                self.expected_pydevd_request('python-ImportError'),
            ]
        self.PYDEVD_CMD = CMD_ADD_EXCEPTION_BREAK
        self.assert_received(self.debugger, removed + [
            self.expected_pydevd_request('python-ImportError\t0\t0\t0'),
            self.expected_pydevd_request('python-RuntimeError\t0\t1\t0'),
        ])

    # TODO: As with the option modes, we've hard-coded the filters
    # in the following tests.  If the supported filters change then
    # we must adjust/extend the tests.

    def test_single_filter_raised(self):
        with self.launched():
            self.send_request(
                filters=[
                    'raised',
                ],
            )
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_response(),
        ])
        self.PYDEVD_CMD = CMD_ADD_EXCEPTION_BREAK
        self.assert_received(self.debugger, [
            self.expected_pydevd_request('python-BaseException\t3\t0\t0'),
        ])

    def test_single_filter_uncaught(self):
        with self.launched():
            self.send_request(
                filters=[
                    'uncaught',
                ],
            )
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_response(),
        ])
        self.PYDEVD_CMD = CMD_ADD_EXCEPTION_BREAK
        self.assert_received(self.debugger, [
            self.expected_pydevd_request('python-BaseException\t0\t1\t0'),
        ])

    def test_multiple_filters_all(self):
        with self.launched():
            self.send_request(
                filters=[
                    'uncaught',
                    'raised',
                ],
            )
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_response(),
        ])
        self.PYDEVD_CMD = CMD_ADD_EXCEPTION_BREAK
        self.assert_received(self.debugger, [
            self.expected_pydevd_request('python-BaseException\t3\t1\t0'),
        ])

    def test_multiple_filters_repeat(self):
        with self.launched():
            self.send_request(
                filters=[
                    'raised',
                    'raised',
                ],
            )
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_response(),
        ])
        self.PYDEVD_CMD = CMD_ADD_EXCEPTION_BREAK
        self.assert_received(self.debugger, [
            self.expected_pydevd_request('python-BaseException\t3\t0\t0'),
        ])

    def test_empty_filters(self):
        with self.launched():
            self.send_request(
                filters=[],
            )

            self.assert_received(self.vsc, [
                self.expected_response()
                # no events
            ])
            self.assert_received(self.debugger, [])

    def test_filters_with_existing_filters(self):
        with self.launched():
            with self.hidden():
                self.PYDEVD_CMD = CMD_ADD_EXCEPTION_BREAK
                self.expected_pydevd_request('python-BaseException\t0\t1\t0')
                self.fix.send_request('setExceptionBreakpoints', dict(
                    filters=[
                        'uncaught',
                    ],
                ))
            self.send_request(
                filters=[
                    'raised',
                ],
            )
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_response(),
        ])
        self.PYDEVD_CMD = CMD_REMOVE_EXCEPTION_BREAK
        removed = [
            self.expected_pydevd_request('python-BaseException'),
        ]
        self.PYDEVD_CMD = CMD_ADD_EXCEPTION_BREAK
        self.assert_received(self.debugger, removed + [
            self.expected_pydevd_request('python-BaseException\t3\t0\t0'),
        ])

    def test_filters_with_existing_options(self):
        with self.launched():
            with self.hidden():
                self.PYDEVD_CMD = CMD_ADD_EXCEPTION_BREAK
                self.expected_pydevd_request('python-ImportError\t0\t1\t0')
                self.expected_pydevd_request('python-BaseException\t3\t0\t0')
                self.fix.send_request('setExceptionBreakpoints', dict(
                    filters=[],
                    exceptionOptions=[
                        {'path': [
                            {'names': ['Python Exceptions']},
                            {'names': ['ImportError']},
                         ],
                         'breakMode': 'unhandled'},
                        {'path': [
                            {'names': ['Python Exceptions']},
                         ],
                         'breakMode': 'always'},
                    ],
                ))
            self.send_request(
                filters=[
                    'raised',
                ],
            )
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_response(),
        ])
        self.PYDEVD_CMD = CMD_REMOVE_EXCEPTION_BREAK
        if self.debugger.received[0].payload == 'python-ImportError':
            removed = [
                self.expected_pydevd_request('python-ImportError'),
                self.expected_pydevd_request('python-BaseException'),
            ]
        else:
            removed = [
                self.expected_pydevd_request('python-BaseException'),
                self.expected_pydevd_request('python-ImportError'),
            ]
        self.PYDEVD_CMD = CMD_ADD_EXCEPTION_BREAK
        self.assert_received(self.debugger, removed + [
            self.expected_pydevd_request('python-BaseException\t3\t0\t0'),
        ])

    def test_filters_with_empty_options(self):
        with self.launched():
            self.send_request(
                filters=[
                    'raised',
                ],
                exceptionOptions=[],
            )
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_response(),
        ])
        self.PYDEVD_CMD = CMD_ADD_EXCEPTION_BREAK
        self.assert_received(self.debugger, [
            self.expected_pydevd_request('python-BaseException\t3\t0\t0'),
        ])

    # TODO: verify behavior
    @unittest.skip('poorly specified')
    def test_options_and_filters_both_provided(self):
        with self.launched():
            self.send_request(
                filters=[
                    'raised',
                ],
                exceptionOptions=[
                    {'path': [
                        {'names': ['Python Exceptions']},
                        {'names': ['ImportError']},
                     ],
                     'breakMode': 'unhandled'},
                ],
            )
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_response(),
        ])
        self.PYDEVD_CMD = CMD_ADD_EXCEPTION_BREAK
        self.assert_received(self.debugger, [
            'python-BaseException\t3\t0\t0',
            'python-ImportError\t0\t1\t0',
        ])


class ExceptionInfoTests(NormalRequestTest, unittest.TestCase):

    COMMAND = 'exceptionInfo'

    # modes: ['never', 'always', 'unhandled', 'userUnhandled']
    #
    # min response:
    #   exceptionId='',
    #   breakMode='',
    #
    # max response:
    #   exceptionId='',
    #   description='',
    #   breakMode='',
    #   details=dict(
    #       message='',
    #       typeName='',
    #       fullTypeName='',
    #       evaluateName='',
    #       stackTrace='',
    #       innerException=[
    #           # details
    #           # details
    #           # ...
    #       ],
    #   ),

    def test_active_exception(self):
        exc = RuntimeError('something went wrong')
        frame = (2, 'spam', 'abc.py', 10)  # (pfid, func, file, line)
        with self.launched():
            with self.hidden():
                tid, _ = self.error('x', exc, frame)
            self.send_request(
                threadId=tid,
            )
            received = self.vsc.received

        # TODO: Is this the right str?
        excstr = "RuntimeError('something went wrong')"
        if sys.version_info[1] < 7:
            excstr = excstr[:-1] + ',)'
        self.assert_vsc_received(received, [
            self.expected_response(
                exceptionId='RuntimeError',
                description=excstr,
                breakMode='unhandled',
                details=dict(
                    message=excstr,
                    typeName='RuntimeError',
                    source='abc.py',
                    stackTrace='\n'.join([
                        '  File "abc.py", line 10, in spam',
                        '    """A decorator indicating abstract methods.',
                        '',
                    ]),
                ),
            ),
        ])
        self.assert_received(self.debugger, [])

    # TODO: verify behavior
    @unittest.skip('poorly specified (broken?)')
    def test_no_exception(self):
        with self.launched():
            with self.hidden():
                tid, _ = self.pause('x')
            self.send_request(
                threadId=tid,
            )
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_response(
            ),
        ])
        self.assert_received(self.debugger, [])

    # TODO: verify behavior
    @unittest.skip('poorly specified (broken?)')
    def test_exception_cleared(self):
        exc = RuntimeError('something went wrong')
        frame = (2, 'spam', 'abc.py', 10)  # (pfid, func, file, line)
        with self.launched():
            with self.hidden():
                tid, thread = self.error('x', exc, frame)
                self.send_debugger_event(
                    CMD_SEND_CURR_EXCEPTION_TRACE_PROCEEDED,
                    str(thread.id),
                )
            self.send_request(
                threadId=tid,
            )
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_response(
            ),
        ])
        self.assert_received(self.debugger, [])


class RunInTerminalTests(NormalRequestTest, unittest.TestCase):

    COMMAND = 'runInTerminal'

    def test_unsupported(self):
        with self.launched():
            self.send_request(
                cwd='.',
                args=['spam'],
            )
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_failure('Unknown command'),
        ])
        self.assert_received(self.debugger, [])


class SourceTests(NormalRequestTest, unittest.TestCase):

    COMMAND = 'source'

    def test_unsupported(self):
        with self.launched():
            self.send_request(
                sourceReference=1,
            )
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_failure('Unknown command'),
        ])
        self.assert_received(self.debugger, [])


class ModulesTests(NormalRequestTest, unittest.TestCase):

    COMMAND = 'modules'

    def test_unsupported(self):
        with self.launched():
            self.send_request()
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_failure('Unknown command'),
        ])
        self.assert_received(self.debugger, [])


class LoadedSourcesTests(NormalRequestTest, unittest.TestCase):

    COMMAND = 'loadedSources'

    def test_unsupported(self):
        with self.launched():
            self.send_request()
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_failure('Unknown command'),
        ])
        self.assert_received(self.debugger, [])


class StepInTargetsTests(NormalRequestTest, unittest.TestCase):

    COMMAND = 'stepInTargets'

    def test_unsupported(self):
        with self.launched():
            self.send_request(
                frameId=1,
            )
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_failure('Unknown command'),
        ])
        self.assert_received(self.debugger, [])


class GotoTargetsTests(NormalRequestTest, unittest.TestCase):

    COMMAND = 'gotoTargets'

    def test_unsupported(self):
        with self.launched():
            self.send_request(
                source={},
                line=0,
            )
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_failure('Unknown command'),
        ])
        self.assert_received(self.debugger, [])


class CompletionsTests(NormalRequestTest, unittest.TestCase):

    COMMAND = 'completions'

    def test_unsupported(self):
        with self.launched():
            self.send_request(
                text='spa',
                column=3,
            )
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_failure('Unknown command'),
        ])
        self.assert_received(self.debugger, [])


##################################
# VSC events

# These events are emitted by ptvsd:
#
#  initialized
#     - after "initialize" response
#  exited
#     - at close
#  terminated
#     - at close
#  stopped
#      - in response to CMD_THREAD_SUSPEND
#  continued
#      - in response to CMD_THREAD_RUN
#  thread
#      - in response to CMD_THREAD_CREATE
#      - in response to CMD_THREAD_KILL
#      - with "threads" response (if new)
#  process
#      - at the end of initialization (after "configurationDone" response)

# These events are never emitted by ptvsd:
#
#  output
#  breakpoint
#  module
#  loadedSource
#  capabilities


##################################
# handled PyDevd events

class PyDevdEventTest(RunningTest):

    CMD = None
    EVENT = None

    def pydevd_payload(self, *args, **kwargs):
        return ''

    def launched(self, port=8888, **kwargs):
        kwargs.setdefault('default_threads', False)
        return super(PyDevdEventTest, self).launched(port, **kwargs)

    def send_event(self, *args, **kwargs):
        handler = kwargs.pop('handler', None)
        text = self.pydevd_payload(*args, **kwargs)
        self.fix.send_event(self.CMD, text, self.EVENT, handler=handler)

    def expected_event(self, **body):
        return self.new_event(self.EVENT, seq=None, **body)


class ProcessCreatedEventTests(PyDevdEventTest, unittest.TestCase):

    CMD = CMD_PROCESS_CREATED
    EVENT = None

    def pydevd_payload(self, pid):
        return '<process/>'

    def test_unsupported(self):
        with self.launched():
            with self.assertRaises(UnsupportedPyDevdCommandError):
                self.send_event(12345)
            received = self.vsc.received

        self.assert_vsc_received(received, [])
        self.assert_received(self.debugger, [])


class ExitEventTests(PyDevdEventTest, unittest.TestCase):

    CMD = CMD_EXIT
    EVENT = None

    def pydevd_payload(self):
        return ''

    def test_unsupported(self):
        with self.launched():
            with self.assertRaises(UnsupportedPyDevdCommandError):
                self.send_event()
            received = self.vsc.received

        self.assert_vsc_received(received, [])
        self.assert_received(self.debugger, [])


class ThreadEventTest(PyDevdEventTest):

    _tid = None

    def send_event(self, *args, **kwargs):
        def handler(msg, _):
            self._tid = msg.body['threadId']
        kwargs['handler'] = handler
        super(ThreadEventTest, self).send_event(*args, **kwargs)
        return self._tid


class ThreadCreateEventTests(ThreadEventTest, unittest.TestCase):

    CMD = CMD_THREAD_CREATE
    EVENT = 'thread'

    def pydevd_payload(self, threadid, name):
        thread = (threadid, name)
        return self.debugger_msgs.format_threads(thread)

    def test_launched(self):
        with self.launched(process=False):
            with self.wait_for_event('process'):
                tid = self.send_event(10, 'spam')
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.new_event('process', **dict(
                name=sys.argv[0],
                systemProcessId=os.getpid(),
                isLocalProcess=True,
                startMethod='launch',
            )),
            self.expected_event(
                reason='started',
                threadId=tid,
            ),
        ])
        self.assert_received(self.debugger, [])

    @unittest.skip('currently not supported')
    def test_attached(self):
        with self.attached(8888, process=False):
            with self.wait_for_event('process'):
                tid = self.send_event(10, 'spam')
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.new_event('process', **dict(
                name=sys.argv[0],
                systemProcessId=os.getpid(),
                isLocalProcess=True,
                startMethod='attach',
            )),
            self.expected_event(
                reason='started',
                threadId=tid,
            ),
        ])
        self.assert_received(self.debugger, [])

    def test_process_one_off(self):
        with self.launched(process=False):
            with self.wait_for_event('process'):
                tid1 = self.send_event(10, 'spam')
            tid2 = self.send_event(11, 'eggs')
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.new_event('process', **dict(
                name=sys.argv[0],
                systemProcessId=os.getpid(),
                isLocalProcess=True,
                startMethod='launch',
            )),
            self.expected_event(
                reason='started',
                threadId=tid1,
            ),
            self.expected_event(
                reason='started',
                threadId=tid2,
            ),
        ])
        self.assert_received(self.debugger, [])

    # TODO: verify behavior
    @unittest.skip('poorly specified')
    def test_exists(self):
        with self.launched():
            with self.hidden():
                _, thread = self.set_thread('x')
            self.send_event(thread.id, 'spam')
            received = self.vsc.received

        self.assert_vsc_received(received, [])
        self.assert_received(self.debugger, [])

    def test_pydevd_name(self):
        self.EVENT = None
        with self.launched():
            self.send_event(10, 'pydevd.spam')
            received = self.vsc.received

        self.assert_vsc_received(received, [])
        self.assert_received(self.debugger, [])

    def test_ptvsd_name(self):
        self.EVENT = None
        with self.launched():
            self.send_event(10, 'ptvsd.spam')
            received = self.vsc.received

        self.assert_vsc_received(received, [])
        self.assert_received(self.debugger, [])


class ThreadKillEventTests(ThreadEventTest, unittest.TestCase):

    CMD = CMD_THREAD_KILL
    EVENT = 'thread'

    def pydevd_payload(self, threadid):
        return str(threadid)

    def test_known(self):
        with self.launched():
            with self.hidden():
                tid, thread = self.set_thread('x')
            self.send_event(thread.id)
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_event(
                reason='exited',
                threadId=tid,
            ),
        ])
        self.assert_received(self.debugger, [])

    def test_unknown(self):
        self.EVENT = None
        with self.launched():
            self.send_event(10)
            received = self.vsc.received

        self.assert_vsc_received(received, [])
        self.assert_received(self.debugger, [])

    def test_pydevd_name(self):
        self.EVENT = None
        with self.launched():
            with self.hidden():
                _, thread = self.set_thread('pydevd.spam')
            self.send_event(thread.id)
            received = self.vsc.received

        self.assert_vsc_received(received, [])
        self.assert_received(self.debugger, [])

    def test_ptvsd_name(self):
        self.EVENT = None
        with self.launched():
            with self.hidden():
                _, thread = self.set_thread('ptvsd.spam')
            self.send_event(thread.id)
            received = self.vsc.received

        self.assert_vsc_received(received, [])
        self.assert_received(self.debugger, [])


class ThreadSuspendEventTests(ThreadEventTest, unittest.TestCase):

    CMD = CMD_THREAD_SUSPEND
    EVENT = 'stopped'

    def pydevd_payload(self, threadid, reason, *frames):
        if not frames:
            frames = [
                # (pfid, func, file, line)
                (2, 'spam', 'abc.py', 10),
                (5, 'eggs', 'xyz.py', 2),
            ]
        return self.debugger_msgs.format_frames(threadid, reason, *frames)

    def test_step_into(self):
        with self.launched():
            with self.hidden():
                _, thread = self.set_thread('x')
            tid = self.send_event(thread.id, CMD_STEP_INTO)
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_event(
                reason='step',
                threadId=tid,
                text=None,
                description=None,
            ),
        ])
        self.assert_received(self.debugger, [])

    def test_step_over(self):
        with self.launched():
            with self.hidden():
                _, thread = self.set_thread('x')
            tid = self.send_event(thread.id, CMD_STEP_OVER)
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_event(
                reason='step',
                threadId=tid,
                text=None,
                description=None,
            ),
        ])
        self.assert_received(self.debugger, [])

    def test_step_return(self):
        with self.launched():
            with self.hidden():
                _, thread = self.set_thread('x')
            tid = self.send_event(thread.id, CMD_STEP_RETURN)
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_event(
                reason='step',
                threadId=tid,
                text=None,
                description=None,
            ),
        ])
        self.assert_received(self.debugger, [])

    def test_caught_exception(self):
        exc = RuntimeError('something went wrong')
        with self.launched():
            with self.hidden():
                _, thread = self.set_thread('x')
            self.set_debugger_response(
                CMD_GET_VARIABLE,
                self.debugger_msgs.format_variables(
                    ('???', '???'),
                    ('???', exc),
                ),
            )
            tid = self.send_event(thread.id, CMD_STEP_CAUGHT_EXCEPTION)
            received = self.vsc.received

        # TODO: Is this the right str?
        excstr = "RuntimeError('something went wrong')"
        if sys.version_info[1] < 7:
            excstr = excstr[:-1] + ',)'
        self.assert_vsc_received(received, [
            self.expected_event(
                reason='exception',
                threadId=tid,
                text='RuntimeError',
                description=excstr,
            ),
        ])
        self.assert_received(self.debugger, [
            self.debugger_msgs.new_request(
                CMD_GET_VARIABLE,
                str(thread.id), '2', 'FRAME', '__exception__'),
        ])

    def test_exception_break(self):
        exc = RuntimeError('something went wrong')
        with self.launched():
            with self.hidden():
                _, thread = self.set_thread('x')
            self.set_debugger_response(
                CMD_GET_VARIABLE,
                self.debugger_msgs.format_variables(
                    ('???', '???'),
                    ('???', exc),
                ),
            )
            tid = self.send_event(thread.id, CMD_ADD_EXCEPTION_BREAK)
            received = self.vsc.received

        # TODO: Is this the right str?
        excstr = "RuntimeError('something went wrong')"
        if sys.version_info[1] < 7:
            excstr = excstr[:-1] + ',)'
        self.assert_vsc_received(received, [
            self.expected_event(
                reason='exception',
                threadId=tid,
                text='RuntimeError',
                description=excstr,
            ),
        ])
        self.assert_received(self.debugger, [
            self.debugger_msgs.new_request(
                CMD_GET_VARIABLE,
                str(thread.id), '2', 'FRAME', '__exception__'),
        ])

    def test_suspend(self):
        with self.launched():
            with self.hidden():
                _, thread = self.set_thread('x')
            tid = self.send_event(thread.id, CMD_THREAD_SUSPEND)
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_event(
                reason='pause',
                threadId=tid,
                text=None,
                description=None,
            ),
        ])
        self.assert_received(self.debugger, [])

    def test_unknown_reason(self):
        with self.launched():
            with self.hidden():
                _, thread = self.set_thread('x')
            tid = self.send_event(thread.id, 99999)
            received = self.vsc.received

        # TODO: Should this fail instead?
        self.assert_vsc_received(received, [
            self.expected_event(
                reason='pause',
                threadId=tid,
                text=None,
                description=None,
            ),
        ])
        self.assert_received(self.debugger, [])

    # TODO: verify behavior
    @unittest.skip('poorly specified')
    def test_no_reason(self):
        with self.launched():
            with self.hidden():
                _, thread = self.set_thread('x')
            tid = self.send_event(thread.id, 'x')
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_event(
                reason='pause',
                threadId=tid,
                text=None,
                description=None,
            ),
        ])
        self.assert_received(self.debugger, [])

    # TODO: verify behavior
    @unittest.skip('poorly specified')
    def test_str_reason(self):
        with self.launched():
            with self.hidden():
                _, thread = self.set_thread('x')
            tid = self.send_event(thread.id, '???')
            received = self.vsc.received

        # TODO: Should this fail instead?
        self.assert_vsc_received(received, [
            self.expected_event(
                reason='pause',
                threadId=tid,
                text=None,
                description=None,
            ),
        ])
        self.assert_received(self.debugger, [])


class ThreadRunEventTests(ThreadEventTest, unittest.TestCase):

    CMD = CMD_THREAD_RUN
    EVENT = 'continued'

    def pydevd_payload(self, threadid, reason):
        return '{}\t{}'.format(threadid, reason)

    def test_basic(self):
        with self.launched():
            with self.hidden():
                _, thread = self.pause('x', *[
                    # (pfid, func, file, line)
                    (2, 'spam', 'abc.py', 10),
                    (5, 'eggs', 'xyz.py', 2),
                ])
            tid = self.send_event(thread.id, '???')
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_event(
                threadId=tid,
            ),
        ])
        self.assert_received(self.debugger, [])


class SendCurrExcTraceEventTests(PyDevdEventTest, unittest.TestCase):

    CMD = CMD_SEND_CURR_EXCEPTION_TRACE
    EVENT = None

    def pydevd_payload(self, thread, exc, frame):
        return self.debugger_msgs.format_exception(thread[0], exc, frame)

    # TODO: Is this right?
    @unittest.skip('now a no-op')
    def test_basic(self):
        exc = RuntimeError('something went wrong')
        frame = (2, 'spam', 'abc.py', 10)  # (pfid, func, file, line)
        with self.launched():
            with self.hidden():
                tid, thread = self.set_thread('x')
            self.send_event(thread, exc, frame)
            received = self.vsc.received

            self.send_request('exceptionInfo', dict(
                threadId=tid,
            ))
            resp = self.vsc.received[-1]

        self.assert_vsc_received(received, [])
        self.assert_received(self.debugger, [])
        self.assertTrue(resp.success, resp.message)
        self.assertEqual(resp.body, dict(
            exceptionId='RuntimeError',
            description='something went wrong',
            breakMode='unhandled',
            details=dict(
                message='something went wrong',
                typeName='RuntimeError',
            ),
        ))


class SendCurrExcTraceProceededEventTests(PyDevdEventTest, unittest.TestCase):

    CMD = CMD_SEND_CURR_EXCEPTION_TRACE_PROCEEDED
    EVENT = None

    def pydevd_payload(self, threadid):
        return str(threadid)

    def test_basic(self):
        exc = RuntimeError('something went wrong')
        frame = (2, 'spam', 'abc.py', 10)  # (pfid, func, file, line)
        #text = self.debugger_msgs.format_exception(thread[0], exc, frame)
        with self.launched():
            with self.hidden():
                #tid, thread = self.set_thread('x')
                #self.fix.send_event(CMD_SEND_CURR_EXCEPTION_TRACE, text)
                tid, thread = self.error('x', exc, frame)
                self.send_request('exceptionInfo', dict(
                    threadId=tid,
                ))
                before = self.vsc.received[-1]

            self.send_event(thread.id)
            received = self.vsc.received

            self.send_request('exceptionInfo', dict(
                threadId=tid,
            ))
            after = self.vsc.received[-1]

        self.assert_vsc_received(received, [])
        self.assert_received(self.debugger, [])
        # The exception got cleared so we do not see RuntimeError.
        self.assertEqual(after.body['exceptionId'], 'BaseException')
        self.assertNotEqual(after.body['exceptionId'],
                            before.body['exceptionId'])


class GetExceptionBreakpointEventTests(PyDevdEventTest, unittest.TestCase):

    CMD = CMD_GET_BREAKPOINT_EXCEPTION
    EVENT = None

    def pydevd_payload(self, tid, exc, frame):
        return self.debugger_msgs.format_exception(tid, exc, frame)

    def test_unsupported(self):
        ptid = 10
        exc = RuntimeError('something went wrong')
        frame = (2, 'spam', 'abc.py', 10)  # (pfid, func, file, line)
        with self.launched():
            with self.assertRaises(UnsupportedPyDevdCommandError):
                self.send_event(ptid, exc, frame)
            received = self.vsc.received

        self.assert_vsc_received(received, [])
        self.assert_received(self.debugger, [])


class ShowConsoleEventTests(PyDevdEventTest, unittest.TestCase):

    CMD = CMD_SHOW_CONSOLE
    EVENT = None

    def pydevd_payload(self, threadid, *frames):
        reason = self.CMD
        return self.debugger_msgs.format_frames(threadid, reason, *frames)

    def test_unsupported(self):
        ptid = 10
        frame = (2, 'spam', 'abc.py', 10)  # (pfid, func, file, line)
        with self.launched():
            with self.assertRaises(UnsupportedPyDevdCommandError):
                self.send_event(ptid, frame)
            received = self.vsc.received

        self.assert_vsc_received(received, [])
        self.assert_received(self.debugger, [])


class WriteToConsoleEventTests(PyDevdEventTest, unittest.TestCase):

    CMD = CMD_WRITE_TO_CONSOLE
    EVENT = None

    def pydevd_payload(self, msg, stdout=True):
        ctx = 1 if stdout else 2
        return '<xml><io s="{}" ctx="{}"/></xml>'.format(msg, ctx)

    @unittest.skip('supported now')  # TODO: write test
    def test_unsupported(self):
        with self.launched():
            with self.assertRaises(UnsupportedPyDevdCommandError):
                self.send_event('output')
            received = self.vsc.received

        self.assert_vsc_received(received, [])
        self.assert_received(self.debugger, [])
