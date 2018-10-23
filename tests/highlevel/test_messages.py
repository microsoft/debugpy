import os
import platform
import sys
import unittest
from textwrap import dedent

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
    CMD_REMOVE_BREAK,
    CMD_REMOVE_EXCEPTION_BREAK,
    CMD_RETURN,
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
    CMD_STEP_INTO_MY_CODE,
    CMD_GET_THREAD_STACK,
    CMD_GET_EXCEPTION_DETAILS,
)

from . import RunningTest
from ptvsd.wrapper import UnsupportedPyDevdCommandError, INITIALIZE_RESPONSE


def fail(msg):
    raise RuntimeError(msg)


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


def _get_cmd_version():
    plat = 'WINDOWS' if platform.system() == 'Windows' else 'UNIX'
    return '1.1\t%s\tID' % plat


class InitializeTests(LifecycleTest, unittest.TestCase):

    @unittest.skip('tested via test_lifecycle.py')
    def test_basic(self):
        with self.lifecycle.demon_running(port=8888):
            req = self.send_request('initialize', {
                'adapterID': 'spam',
            })
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.new_response(req, **INITIALIZE_RESPONSE),
            self.new_event(1, 'initialized'),
        ])
        self.assert_received(self.debugger, [])


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
    PYDEVD_CMD = CMD_GET_THREAD_STACK

    def pydevd_payload(self, threadid, *frames):
        return self.debugger_msgs.format_frames(threadid, 'pause', *frames)

    def test_basic(self):
        frames = [
            # (pfid, func, file, line)
            (2, 'spam', 'abc.py', 10),
            (5, 'eggs', 'xyz.py', 2),
        ]
        with self.launched():
            with self.hidden():
                tid, thread = self.set_thread('x')
                self.suspend(thread, CMD_THREAD_SUSPEND, *frames)
            self.set_debugger_response(thread.id, *frames)
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
                        'source': {'path': 'abc.py', 'sourceReference': 0},
                        'line': 10,
                        'column': 1,
                    },
                    {
                        'id': 2,
                        'name': 'eggs',
                        'source': {'path': 'xyz.py', 'sourceReference': 0},
                        'line': 2,
                        'column': 1,
                    },
                ],
                totalFrames=2,
            ),
            # no events
        ])
        self.assert_received(self.debugger, [
            self.debugger_msgs.new_request(self.PYDEVD_CMD, str(thread.id)),
        ])

    def test_one_frame(self):
        frames = [
            # (pfid, func, file, line)
            (2, 'spam', 'abc.py', 10),
        ]
        with self.launched():
            with self.hidden():
                tid, thread = self.set_thread('x')
                self.suspend(thread, CMD_THREAD_SUSPEND, *frames)
            self.set_debugger_response(thread.id, *frames)
            self.send_request(
                threadId=tid,
            )
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_response(
                stackFrames=[
                    {
                        'id': 1,
                        'name': 'spam',
                        'source': {'path': 'abc.py', 'sourceReference': 0},
                        'line': 10,
                        'column': 1,
                    },
                ],
                totalFrames=1,
            ),
            # no events
        ])
        self.assert_received(self.debugger, [
            self.debugger_msgs.new_request(self.PYDEVD_CMD, str(thread.id)),
        ])

    def test_with_frame_format(self):
        frames = [
            # (pfid, func, file, line)
            (2, 'spam', 'abc.py', 10),
            (5, 'eggs', 'xyz.py', 2),
        ]
        with self.launched():
            with self.hidden():
                tid, thread = self.set_thread('x')
                self.suspend(thread, CMD_THREAD_SUSPEND, *frames)
            self.set_debugger_response(thread.id, *frames)
            self.send_request(
                threadId=tid,
                format={
                    'module': True,
                    'line': True,
                }
                #startFrame=1,
                #levels=1,
            )
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_response(
                stackFrames=[
                    {
                        'id': 1,
                        'name': 'abc.spam : 10',
                        'source': {'path': 'abc.py', 'sourceReference': 0},
                        'line': 10,
                        'column': 1,
                    },
                    {
                        'id': 2,
                        'name': 'xyz.eggs : 2',
                        'source': {'path': 'xyz.py', 'sourceReference': 0},
                        'line': 2,
                        'column': 1,
                    },
                ],
                totalFrames=2,
            ),
            # no events
        ])
        self.assert_received(self.debugger, [
            self.debugger_msgs.new_request(self.PYDEVD_CMD, str(thread.id)),
        ])

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
            self.send_request(
                threadId=12345,
            )
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_failure('Thread 12345 not found'),
        ])
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
                        'evaluateName': 'ham',
                        'name': 'ham',
                        'type': 'list',
                        'value': '[1, 2, 3]',
                        'variablesReference': 2,
                    },
                    {
                        'evaluateName': 'spam',
                        'name': 'spam',
                        'type': 'str',
                        'value': "'eggs'",
                        'presentationHint': {
                            'attributes': ['rawString'],
                        },
                    },
                    {
                        'evaluateName': 'x',
                        'name': 'x',
                        'type': 'bool',
                        'value': 'True',
                    },
                    {
                        'evaluateName': 'y',
                        'name': 'y',
                        'type': 'int',
                        'value': '42',
                    },
                    {
                        'evaluateName': 'z',
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

    def test_invalid_var_ref(self):
        with self.launched():
            with self.hidden():
                _, thread = self.pause('t', *[
                    # (pfid, func, file, line)
                    (2, 'spam', 'abc.py', 10),  # VSC frame ID 1
                    (5, 'eggs', 'xyz.py', 2),  # VSC frame ID 2
                ])
            self.send_request(
                # should NOT match variable or frame ID
                variablesReference=12345,
            )
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_failure('Variable 12345 not found in frame'),
            # no events
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

    def test_invalid_var_ref(self):
        with self.launched():
            with self.hidden():
                _, thread = self.pause('t', *[
                    # (pfid, func, file, line)
                    (2, 'spam', 'abc.py', 10),  # VSC frame ID 1
                    (5, 'eggs', 'xyz.py', 2),  # VSC frame ID 2
                ])
            self.send_request(
                # should NOT match any variable or frame ID
                variablesReference=12345,
                name='spam',
                value='eggs',
            )
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_failure('Variable 12345 not found in frame'),
            # no events
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

    def test_multiline(self):
        with self.launched():
            with self.hidden():
                _, thread = self.pause('x', *[
                    # (pfid, func, file, line)
                    (2, 'spam', 'abc.py', 10),  # VSC frame ID 1
                    (5, 'eggs', 'xyz.py', 2),  # VSC frame ID 2
                ])
            expr = dedent("""
            def my_sqr(x):
                return x*x
            my_sqr(7)""")
            self.set_debugger_response(
                (expr, 49),
            )
            self.send_request(
                frameId=2,
                expression=expr,
                context=None,
            )
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_response(
                type='int',
                result='49',
            ),
            # no events
        ])

        expr_rec = '@LINE@def my_sqr(x):@LINE@    return x*x@LINE@my_sqr(7)'
        self.assert_received(self.debugger, [
            self.expected_pydevd_request(
                '{}\t5\tLOCAL\t{}\t1'.format(thread.id, expr_rec)),
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

    def test_pause(self):
        with self.launched():
            with self.hidden():
                threads = self.set_threads('spam', 'eggs', 'abc')
            tid, thread = threads[0]
            self.send_request(
                threadId=tid,
            )
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_response(),
            # no events
        ])

        expected = [self.expected_pydevd_request('*')]

        self.assert_received_unordered_payload(self.debugger, expected)


class ContinueTests(NormalRequestTest, unittest.TestCase):

    COMMAND = 'continue'
    PYDEVD_CMD = CMD_THREAD_RUN
    PYDEVD_RESP = None

    def test_basic(self):
        frames = [
            (2, 'spam', 'abc.py', 10),
        ]
        with self.launched():
            with self.hidden():
                tid, thread = self.pause('x', *frames)
            self.send_request(
                threadId=tid,
            )
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_response(allThreadsContinued=True),
            # no events
        ])

        expected = [self.debugger_msgs.new_request(self.PYDEVD_CMD, '*')]
        self.assert_contains(self.debugger.received, expected,
                             parser=self.debugger.protocol)


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
    PYDEVD_CMD = CMD_STEP_INTO_MY_CODE
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
                '1\tpython-line\tspam.py\t10\tNone\tNone\tNone\tNone\tNone\tALL'), # noqa
            self.expected_pydevd_request(
                '2\tpython-line\tspam.py\t15\tNone\ti == 3\tNone\tNone\tNone\tALL'), # noqa
            self.debugger_msgs.new_request(CMD_VERSION, _get_cmd_version()),
        ])

    def test_with_hit_condition(self):
        with self.launched():
            self.send_request(
                source={'path': 'spam.py'},
                breakpoints=[
                    {'line': '10',
                     'hitCondition': '5'},
                    {'line': '15',
                     'hitCondition': ' ==5'},
                    {'line': '20',
                     'hitCondition': '> 5'},
                    {'line': '25',
                     'hitCondition': '% 5'},
                    {'line': '30',
                     'hitCondition': 'x'}
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
                    {'id': 3,
                     'verified': True,
                     'line': '20'},
                    {'id': 4,
                     'verified': True,
                     'line': '25'},
                    {'id': 5,
                     'verified': True,
                     'line': '30'},
                ],
            ),
            # no events
        ])
        self.PYDEVD_CMD = CMD_SET_BREAK
        self.assert_received(self.debugger, [
            self.expected_pydevd_request(
                '1\tpython-line\tspam.py\t10\tNone\tNone\tNone\t@HIT@ == 5\tNone\tALL'), # noqa
            self.expected_pydevd_request(
                '2\tpython-line\tspam.py\t15\tNone\tNone\tNone\t@HIT@ ==5\tNone\tALL'), # noqa
            self.expected_pydevd_request(
                '3\tpython-line\tspam.py\t20\tNone\tNone\tNone\t@HIT@ > 5\tNone\tALL'), # noqa
            self.expected_pydevd_request(
             '4\tpython-line\tspam.py\t25\tNone\tNone\tNone\t@HIT@ % 5 == 0\tNone\tALL'), # noqa
            self.expected_pydevd_request(
                '5\tpython-line\tspam.py\t30\tNone\tNone\tNone\tx\tNone\tALL'),
            self.debugger_msgs.new_request(CMD_VERSION, _get_cmd_version()),
        ])

    def test_with_logpoint(self):
        with self.launched():
            self.send_request(
                source={'path': 'spam.py'},
                breakpoints=[
                    {'line': '10',
                     'logMessage': '5'},
                    {'line': '15',
                     'logMessage': 'Hello World'},
                    {'line': '20',
                     'logMessage': '{a}'},
                    {'line': '25',
                     'logMessage': '{a}+{b}=Something'}
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
                    {'id': 3,
                     'verified': True,
                     'line': '20'},
                    {'id': 4,
                     'verified': True,
                     'line': '25'}
                ],
            ),
            # no events
        ])
        self.PYDEVD_CMD = CMD_SET_BREAK
        self.assert_received(self.debugger, [
            self.expected_pydevd_request(
                '1\tpython-line\tspam.py\t10\tNone\tNone\t' + repr("5") + '\tNone\tTrue\tALL'), # noqa
            self.expected_pydevd_request(
                '2\tpython-line\tspam.py\t15\tNone\tNone\t' + repr("Hello World") + '\tNone\tTrue\tALL'), # noqa
            self.expected_pydevd_request(
                '3\tpython-line\tspam.py\t20\tNone\tNone\t"{}".format(a)\tNone\tTrue\tALL'), # noqa
            self.expected_pydevd_request(
             '4\tpython-line\tspam.py\t25\tNone\tNone\t"{}+{}=Something".format(a, b)\tNone\tTrue\tALL'), # noqa
            self.debugger_msgs.new_request(CMD_VERSION, _get_cmd_version()),
        ])

    def test_with_existing(self):
        with self.launched():
            with self.hidden():
                self.PYDEVD_CMD = CMD_SET_BREAK
                p1 = self.expected_pydevd_request(
                    '1\tpython-line\tspam.py\t10\tNone\tNone\tNone\tNone\tNone\tALL') # noqa
                p2 = self.expected_pydevd_request(
                    '2\tpython-line\tspam.py\t17\tNone\tNone\tNone\tNone\tNone\tALL') # noqa
                with self.expect_debugger_command(CMD_VERSION):
                    self.fix.send_request('setBreakpoints', dict(
                        source={'path': 'spam.py'},
                        breakpoints=[
                            {'line': '10'},
                            {'line': '17'},
                        ],
                    ))
                self.wait_for_pydevd(p1, p2)
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
                '3\tpython-line\tspam.py\t113\tNone\tNone\tNone\tNone\tNone\tALL'), # noqa
            self.expected_pydevd_request(
                '4\tpython-line\tspam.py\t2\tNone\tNone\tNone\tNone\tNone\tALL'), # noqa
            self.expected_pydevd_request(
                '5\tpython-line\tspam.py\t10\tNone\tNone\tNone\tNone\tNone\tALL'), # noqa
            self.debugger_msgs.new_request(CMD_VERSION, _get_cmd_version()),
        ])

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
                '1\tpython-line\tspam.py\t10\tNone\tNone\tNone\tNone\tNone\tALL'), # noqa
            self.debugger_msgs.new_request(CMD_VERSION, _get_cmd_version()),
            self.expected_pydevd_request(
                '2\tpython-line\teggs.py\t17\tNone\tNone\tNone\tNone\tNone\tALL'), # noqa
            self.debugger_msgs.new_request(CMD_VERSION, _get_cmd_version()),
        ])

    def test_vs_django(self):
        with self.launched(args={'options': 'DJANGO_DEBUG=True'}):
            self.send_request(
                source={'path': 'spam.py'},
                breakpoints=[{'line': '10'}],
            )
            self.send_request(
                source={'path': 'eggs.html'},
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
        ])

        self.PYDEVD_CMD = CMD_SET_BREAK
        self.assert_received(self.debugger, [
            self.expected_pydevd_request(
                '1\tpython-line\tspam.py\t10\tNone\tNone\tNone\tNone\tNone\tALL'), # noqa
            self.debugger_msgs.new_request(CMD_VERSION, _get_cmd_version()),
            self.expected_pydevd_request(
                '2\tdjango-line\teggs.html\t17\tNone\tNone\tNone\tNone\tNone\tALL'), # noqa
            self.debugger_msgs.new_request(CMD_VERSION, _get_cmd_version()),
        ])

    def test_vs_django_logpoint(self):
        with self.launched(args={'options': 'DJANGO_DEBUG=True'}):
            self.send_request(
                source={'path': 'spam.py'},
                breakpoints=[{'line': '10', 'logMessage': 'Hello World'}],
            )
            self.send_request(
                source={'path': 'eggs.html'},
                breakpoints=[{'line': '17', 'logMessage': 'Hello Django World'}], # noqa
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
        ])

        self.PYDEVD_CMD = CMD_SET_BREAK
        self.assert_received(self.debugger, [
            self.expected_pydevd_request(
                '1\tpython-line\tspam.py\t10\tNone\tNone\t' + repr("Hello World") + '\tNone\tTrue\tALL'), # noqa
            self.debugger_msgs.new_request(CMD_VERSION, _get_cmd_version()),
            self.expected_pydevd_request(
                '2\tdjango-line\teggs.html\t17\tNone\tNone\t' + repr("Hello Django World") + '\tNone\tTrue\tALL'), # noqa
            self.debugger_msgs.new_request(CMD_VERSION, _get_cmd_version()),
        ])

    def test_vs_flask_jinja2(self):
        with self.launched(args={'options': 'FLASK_DEBUG=True'}):
            self.send_request(
                source={'path': 'spam.py'},
                breakpoints=[{'line': '10'}],
            )
            self.send_request(
                source={'path': 'eggs.html'},
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
        ])

        self.PYDEVD_CMD = CMD_SET_BREAK
        self.assert_received(self.debugger, [
            self.expected_pydevd_request(
                '1\tpython-line\tspam.py\t10\tNone\tNone\tNone\tNone\tNone\tALL'), # noqa
            self.debugger_msgs.new_request(CMD_VERSION, _get_cmd_version()),
            self.expected_pydevd_request(
                '2\tjinja2-line\teggs.html\t17\tNone\tNone\tNone\tNone\tNone\tALL'), # noqa
            self.debugger_msgs.new_request(CMD_VERSION, _get_cmd_version()),
        ])

    def test_vs_flask_jinja2_logpoint(self):
        with self.launched(args={'options': 'FLASK_DEBUG=True'}):
            self.send_request(
                source={'path': 'spam.py'},
                breakpoints=[{'line': '10', 'logMessage': 'Hello World'}],
            )
            self.send_request(
                source={'path': 'eggs.html'},
                breakpoints=[{'line': '17', 'logMessage': 'Hello Jinja World'}], # noqa
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
        ])

        self.PYDEVD_CMD = CMD_SET_BREAK
        self.assert_received(self.debugger, [
            self.expected_pydevd_request(
                '1\tpython-line\tspam.py\t10\tNone\tNone\t' + repr("Hello World") + '\tNone\tTrue\tALL'), # noqa
            self.debugger_msgs.new_request(CMD_VERSION, _get_cmd_version()),
            self.expected_pydevd_request(
                '2\tjinja2-line\teggs.html\t17\tNone\tNone\t' + repr("Hello Jinja World") + '\tNone\tTrue\tALL'), # noqa
            self.debugger_msgs.new_request(CMD_VERSION, _get_cmd_version()),
        ])

    def test_vsc_flask_jinja2(self):
        with self.launched(args={'debugOptions': ['Flask']}):
            self.send_request(
                source={'path': 'spam.py'},
                breakpoints=[{'line': '10'}],
            )
            self.send_request(
                source={'path': 'eggs.html'},
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
        ])

        self.PYDEVD_CMD = CMD_SET_BREAK
        self.assert_received(self.debugger, [
            self.expected_pydevd_request(
                '1\tpython-line\tspam.py\t10\tNone\tNone\tNone\tNone\tNone\tALL'), # noqa
            self.debugger_msgs.new_request(CMD_VERSION, _get_cmd_version()),
            self.expected_pydevd_request(
                '2\tjinja2-line\teggs.html\t17\tNone\tNone\tNone\tNone\tNone\tALL'), # noqa
            self.debugger_msgs.new_request(CMD_VERSION, _get_cmd_version()),
        ])

    def test_vsc_jinja2(self):
        with self.launched(args={'debugOptions': ['Jinja']}):
            self.send_request(
                source={'path': 'spam.py'},
                breakpoints=[{'line': '10'}],
            )
            self.send_request(
                source={'path': 'eggs.html'},
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
        ])

        self.PYDEVD_CMD = CMD_SET_BREAK
        self.assert_received(self.debugger, [
            self.expected_pydevd_request(
                '1\tpython-line\tspam.py\t10\tNone\tNone\tNone\tNone\tNone\tALL'), # noqa
            self.debugger_msgs.new_request(CMD_VERSION, _get_cmd_version()),
            self.expected_pydevd_request(
                '2\tjinja2-line\teggs.html\t17\tNone\tNone\tNone\tNone\tNone\tALL'), # noqa
            self.debugger_msgs.new_request(CMD_VERSION, _get_cmd_version()),
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
    # have a programmatic alternative that is very readable.

    # NOTE: The mode here depends on the default value of DEBUG_STDLIB.
    # When this test was written it was assumed the DEBUG_STDLIB = False.
    # this means ignore_stdlib arg to pydevd must be 1

    def test_single_option_single_path_mode_never(self):
        path = {
            'names': ['Python Exceptions'],
        }
        self._check_option(
            [path],
            'never',
            ['python-BaseException\t0\t0\t1'],
        )

    def test_single_option_single_path_mode_always(self):
        path = {
            'names': ['Python Exceptions'],
        }
        self._check_option(
            [path],
            'always',
            ['python-BaseException\t1\t0\t1'],
        )

    def test_single_option_single_path_mode_unhandled(self):
        path = {
            'names': ['Python Exceptions'],
        }
        self._check_option(
            [path],
            'unhandled',
            ['python-BaseException\t0\t1\t1'],
        )

    def test_single_option_single_path_mode_userUnhandled(self):
        path = {
            'names': ['Python Exceptions'],
        }
        self._check_option(
            [path],
            'userUnhandled',
            ['python-BaseException\t0\t1\t1'],
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
            ['python-BaseException\t3\t0\t1'],
        )

    def test_single_option_shallow_path(self):
        path = [
            {'names': ['Python Exceptions']},
            {'names': ['ImportError']},
        ]
        self._check_option(path, 'always', [
            'python-ImportError\t1\t0\t1',
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
            'python-ImportError\t1\t0\t1',
            'python-RuntimeError\t1\t0\t1',
            'python-ValueError\t1\t0\t1',
            'python-MyError\t1\t0\t1',
        ])

    # TODO: verify behavior
    @unittest.skip('poorly specified')
    def test_single_option_multiple_names(self):
        path = [
            {'names': ['Python Exceptions']},
            {'names': ['ImportError', 'RuntimeError', 'ValueError']},
        ]
        self._check_option(path, 'always', [
            'python-ImportError\t1\t0\t1',
            'python-RuntimeError\t1\t0\t1',
            'python-ValueError\t1\t0\t1',
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
            'python-ImportError\t1\t0\t1',
            # ignored
            # deep path
            'python-ModuleNotFoundError\t0\t1\t1',
            'python-RuntimeError\t0\t1\t1',
            'python-MyError\t0\t1\t1',
            # multiple names
            'python-ValueError\t0\t0\t1',
            'python-IndexError\t0\t0\t1',
            # catch-all
            'python-BaseException\t0\t1\t1',
        ])

    def test_options_with_existing_filters(self):
        with self.launched():
            with self.hidden():
                self.PYDEVD_CMD = CMD_ADD_EXCEPTION_BREAK
                p1 = self.expected_pydevd_request(
                    'python-BaseException\t0\t1\t1',
                )
                self.fix.send_request('setExceptionBreakpoints', dict(
                    filters=[
                        'uncaught',
                    ],
                ))
                self.wait_for_pydevd(p1)
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
            self.expected_pydevd_request('python-ImportError\t0\t0\t1'),
            self.expected_pydevd_request('python-RuntimeError\t1\t0\t1'),
        ])

    def test_options_with_existing_options(self):
        with self.launched():
            with self.hidden():
                self.PYDEVD_CMD = CMD_ADD_EXCEPTION_BREAK
                p1 = self.expected_pydevd_request(
                    'python-ImportError\t0\t1\t1',
                )
                p2 = self.expected_pydevd_request(
                    'python-BaseException\t1\t0\t1',
                )
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
                self.wait_for_pydevd(p1, p2)
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
            self.expected_pydevd_request('python-ImportError\t0\t0\t1'),
            self.expected_pydevd_request('python-RuntimeError\t0\t1\t1'),
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
            self.expected_pydevd_request('python-BaseException\t1\t0\t1'),
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
            self.expected_pydevd_request('python-BaseException\t0\t1\t1'),
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
            self.expected_pydevd_request('python-BaseException\t1\t1\t1'),
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
            self.expected_pydevd_request('python-BaseException\t1\t0\t1'),
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
                p1 = self.expected_pydevd_request(
                    'python-BaseException\t0\t1\t1',
                )
                self.fix.send_request('setExceptionBreakpoints', dict(
                    filters=[
                        'uncaught',
                    ],
                ))
                self.wait_for_pydevd(p1)
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
            self.expected_pydevd_request('python-BaseException\t1\t0\t1'),
        ])

    def test_filters_with_existing_options(self):
        with self.launched():
            with self.hidden():
                self.PYDEVD_CMD = CMD_ADD_EXCEPTION_BREAK
                p1 = self.expected_pydevd_request(
                    'python-ImportError\t0\t1\t1',
                )
                p2 = self.expected_pydevd_request(
                    'python-BaseException\t1\t0\t1',
                )
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
                self.wait_for_pydevd(p1, p2)
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
            self.expected_pydevd_request('python-BaseException\t1\t0\t1'),
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
            self.expected_pydevd_request('python-BaseException\t1\t0\t1'),
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
            'python-BaseException\t1\t0\t1',
            'python-ImportError\t0\t1\t1',
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

    PYDEVD_CMD = CMD_GET_EXCEPTION_DETAILS

    def pydevd_payload(self, threadid, *args):
        if self.PYDEVD_CMD == CMD_GET_EXCEPTION_DETAILS:
            return self.debugger_msgs.format_exception_details(
                threadid, args[0], *args[1:])
        else:
            return self.debugger_msgs.format_variables(*args)

    def test_active_exception(self):
        exc = RuntimeError('something went wrong')
        lineno = fail.__code__.co_firstlineno + 1
        frame = (2, 'fail', __file__, lineno)  # (pfid, func, file, line)
        with self.launched():
            with self.hidden():
                tid, thread = self.error('x', exc, frame)
            self.set_debugger_response(thread.id, exc, frame)
            self.send_request(
                threadId=tid,
            )
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_response(
                exceptionId='RuntimeError',
                description='something went wrong',
                breakMode='unhandled',
                details=dict(
                    message='something went wrong',
                    typeName='RuntimeError',
                    source=__file__,
                    stackTrace='\n'.join([
                        '  File "{}", line {}, in fail'.format(__file__,
                                                               lineno),
                        '    raise RuntimeError(msg)',
                        '',
                    ]),
                ),
            ),
        ])
        self.assert_received(self.debugger, [
            self.debugger_msgs.new_request(
                CMD_GET_EXCEPTION_DETAILS, str(thread.id)),
        ])

    def test_no_exception(self):
        exc = RuntimeError('something went wrong')
        lineno = fail.__code__.co_firstlineno + 1
        frame = (2, 'fail', __file__, lineno)  # (pfid, func, file, line)
        with self.launched():
            with self.hidden():
                tid, thread = self.error('x', exc, frame)
            self.set_debugger_response(thread.id, exc, frame)
            self.send_request(
                threadId=tid,
            )
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_response(
                exceptionId='RuntimeError',
                description='something went wrong',
                breakMode='unhandled',
                details=dict(
                    typeName='RuntimeError',
                    message='something went wrong',
                    source=__file__,
                    stackTrace='\n'.join([
                        '  File "{}", line {}, in fail'.format(__file__,
                                                               lineno),
                        '    raise RuntimeError(msg)',
                        '',
                    ]),
                ),
            ),
        ])
        self.assert_received(self.debugger, [
            self.debugger_msgs.new_request(
                CMD_GET_EXCEPTION_DETAILS, str(thread.id)),
        ])


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
                sourceReference=0,
            )
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_failure('Source unavailable'),
        ])
        self.assert_received(self.debugger, [])


class ModulesTests(NormalRequestTest, unittest.TestCase):

    COMMAND = 'modules'

    def test_no_modules(self):
        with self.launched():
            self.send_request()
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_response(
                modules=[],
                totalModules=0
            ),
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
            self.new_event('ptvsd_process', **dict(
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
            self.new_event('ptvsd_process', **dict(
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
            self.new_event('ptvsd_process', **dict(
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
                preserveFocusHint=False,
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
                preserveFocusHint=False,
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
                preserveFocusHint=False,
            ),
        ])
        self.assert_received(self.debugger, [])

    def test_caught_exception(self):
        exc = RuntimeError('something went wrong')
        with self.launched():
            with self.hidden():
                _, thread = self.set_thread('x')
            self.set_debugger_response(
                CMD_GET_EXCEPTION_DETAILS,
                self.debugger_msgs.format_exception_details(
                    thread.id, exc
                ),
            )
            tid = self.send_event(thread.id, CMD_STEP_CAUGHT_EXCEPTION)
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_event(
                reason='exception',
                threadId=tid,
                text='RuntimeError',
                description='something went wrong',
                preserveFocusHint=False,
            ),
        ])
        self.assert_received(self.debugger, [
            self.debugger_msgs.new_request(
                CMD_GET_EXCEPTION_DETAILS,
                str(thread.id)),
        ])

    def test_exception_break(self):
        exc = RuntimeError('something went wrong')
        with self.launched():
            with self.hidden():
                _, thread = self.set_thread('x')
            self.set_debugger_response(
                CMD_GET_EXCEPTION_DETAILS,
                self.debugger_msgs.format_exception_details(
                    thread.id, exc
                ),
            )
            tid = self.send_event(thread.id, CMD_ADD_EXCEPTION_BREAK)
            received = self.vsc.received

        self.assert_vsc_received(received, [
            self.expected_event(
                reason='exception',
                threadId=tid,
                text='RuntimeError',
                description='something went wrong',
                preserveFocusHint=False,
            ),
        ])
        self.assert_received(self.debugger, [
            self.debugger_msgs.new_request(
                CMD_GET_EXCEPTION_DETAILS,
                str(thread.id)),
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
                preserveFocusHint=True,
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
                preserveFocusHint=True,
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
                preserveFocusHint=True,
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
                preserveFocusHint=True,
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


class GetExceptionBreakpointEventTests(PyDevdEventTest, unittest.TestCase):

    CMD = CMD_GET_BREAKPOINT_EXCEPTION
    EVENT = None

    def pydevd_payload(self, tid, exc_type, stacktrace):
        return self.debugger_msgs.format_breakpoint_exception(tid, exc_type, stacktrace)

    def test_basic(self):
        trace = [('abc.py', 10, 'spam', 'eggs'), ]  # (file, line, func, obj)
        with self.launched():
            self.send_event(10, 'RuntimeError', trace)
            received = self.vsc.received

        # Note: We don't send any events to client. So this should be empty.
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

class UnsupportedPyDevdEventTests(PyDevdEventTest, unittest.TestCase):

    CMD = 12345
    EVENT = None

    def pydevd_paylaod(self, msg):
        return msg

    def test_unsupported(self):
        with self.launched():
            with self.assertRaises(UnsupportedPyDevdCommandError):
                self.send_event('unsupported')
            received = self.vsc.received

        self.assert_vsc_received(received, [])
        self.assert_received(self.debugger, [])
