# coding: utf-8
from collections import namedtuple
import json
from os.path import normcase
import os.path
import sys
import time

import pytest

from _pydev_bundle.pydev_localhost import get_socket_name
from _pydevd_bundle._debug_adapter import pydevd_schema, pydevd_base_schema
from _pydevd_bundle._debug_adapter.pydevd_base_schema import from_json
from _pydevd_bundle._debug_adapter.pydevd_schema import (ThreadEvent, ModuleEvent, OutputEvent,
    ExceptionOptions, Response, StoppedEvent, ContinuedEvent, ProcessEvent, InitializeRequest,
    InitializeRequestArguments, TerminateArguments, TerminateRequest, TerminatedEvent)
from _pydevd_bundle.pydevd_comm_constants import file_system_encoding
from _pydevd_bundle.pydevd_constants import (int_types, IS_64BIT_PROCESS,
    PY_VERSION_STR, PY_IMPL_VERSION_STR, PY_IMPL_NAME)
from tests_python import debugger_unittest
from tests_python.debug_constants import TEST_CHERRYPY, IS_PY2, TEST_DJANGO, TEST_FLASK, IS_PY26, \
    IS_PY27, IS_CPYTHON
from tests_python.debugger_unittest import (IS_JYTHON, IS_APPVEYOR, overrides,
    get_free_port, wait_for_condition)

pytest_plugins = [
    str('tests_python.debugger_fixtures'),
]

_JsonHit = namedtuple('_JsonHit', 'thread_id, frame_id, stack_trace_response')

pytestmark = pytest.mark.skipif(IS_JYTHON, reason='Single notification is not OK in Jython (investigate).')

# Note: in reality must be < int32, but as it's created sequentially this should be
# a reasonable number for tests.
MAX_EXPECTED_ID = 10000


class _MessageWithMark(object):

    def __init__(self, msg):
        self.msg = msg
        self.marked = False


class JsonFacade(object):

    def __init__(self, writer, send_json_startup_messages=True):
        self.writer = writer
        writer.reader_thread.accept_xml_messages = False
        if send_json_startup_messages:
            writer.write_set_protocol('http_json')
            writer.write_multi_threads_single_notification(True)
        self._all_json_messages_found = []
        self._sent_launch_or_attach = False

    def mark_messages(self, expected_class, accept_message=lambda obj:True):
        ret = []
        for message_with_mark in self._all_json_messages_found:
            if not message_with_mark.marked:
                if isinstance(message_with_mark.msg, expected_class):
                    if accept_message(message_with_mark.msg):
                        message_with_mark.marked = True
                        ret.append(message_with_mark.msg)
        return ret

    def wait_for_json_message(self, expected_class, accept_message=lambda obj:True):

        def accept_json_message(msg):
            if msg.startswith('{'):
                decoded_msg = from_json(msg)

                self._all_json_messages_found.append(_MessageWithMark(decoded_msg))

                if isinstance(decoded_msg, expected_class):
                    if accept_message(decoded_msg):
                        return True
            return False

        msg = self.writer.wait_for_message(accept_json_message, unquote_msg=False, expect_xml=False)
        return from_json(msg)

    def wait_for_response(self, request):
        response_class = pydevd_base_schema.get_response_class(request)

        def accept_message(response):
            if isinstance(request, dict):
                if response.request_seq == request['seq']:
                    return True
            else:
                if response.request_seq == request.seq:
                    return True
            return False

        return self.wait_for_json_message((response_class, Response), accept_message)

    def write_request(self, request):
        seq = self.writer.next_seq()
        if isinstance(request, dict):
            request['seq'] = seq
            self.writer.write_with_content_len(json.dumps(request))
        else:
            request.seq = seq
            self.writer.write_with_content_len(request.to_json())
        return request

    def write_make_initial_run(self):
        if not self._sent_launch_or_attach:
            self.write_launch()

        configuration_done_request = self.write_request(pydevd_schema.ConfigurationDoneRequest())
        return self.wait_for_response(configuration_done_request)

    def write_list_threads(self):
        return self.wait_for_response(self.write_request(pydevd_schema.ThreadsRequest()))

    def wait_for_terminated(self):
        return self.wait_for_json_message(TerminatedEvent)

    def wait_for_thread_stopped(self, reason='breakpoint', line=None, file=None, name=None):
        '''
        :param file:
            utf-8 bytes encoded file or unicode
        '''
        stopped_event = self.wait_for_json_message(StoppedEvent)
        assert stopped_event.body.reason == reason
        json_hit = self.get_stack_as_json_hit(stopped_event.body.threadId)
        if file is not None:
            path = json_hit.stack_trace_response.body.stackFrames[0]['source']['path']
            if IS_PY2:
                if isinstance(file, bytes):
                    file = file.decode('utf-8')
                if isinstance(path, bytes):
                    path = path.decode('utf-8')

            assert path.endswith(file)
        if name is not None:
            assert json_hit.stack_trace_response.body.stackFrames[0]['name'] == name
        if line is not None:
            found_line = json_hit.stack_trace_response.body.stackFrames[0]['line']
            if not isinstance(line, (tuple, list)):
                line = [line]
            assert found_line in line, 'Expect to break at line: %s. Found: %s' % (line, found_line)
        return json_hit

    def write_set_breakpoints(
            self,
            lines,
            filename=None,
            line_to_info=None,
            success=True,
            verified=True,
            send_launch_if_needed=True,
            expected_lines_in_response=None,
        ):
        '''
        Adds a breakpoint.
        '''
        if send_launch_if_needed and not self._sent_launch_or_attach:
            self.write_launch()

        if isinstance(lines, int):
            lines = [lines]

        if line_to_info is None:
            line_to_info = {}

        if filename is None:
            filename = self.writer.get_main_filename()

        if isinstance(filename, bytes):
            filename = filename.decode(file_system_encoding)  # file is in the filesystem encoding but protocol needs it in utf-8
            filename = filename.encode('utf-8')

        source = pydevd_schema.Source(path=filename)
        breakpoints = []
        for line in lines:
            condition = None
            hit_condition = None
            log_message = None

            if line in line_to_info:
                line_info = line_to_info.get(line)
                condition = line_info.get('condition')
                hit_condition = line_info.get('hit_condition')
                log_message = line_info.get('log_message')

            breakpoints.append(pydevd_schema.SourceBreakpoint(
                line, condition=condition, hitCondition=hit_condition, logMessage=log_message).to_dict())

        arguments = pydevd_schema.SetBreakpointsArguments(source, breakpoints)
        request = pydevd_schema.SetBreakpointsRequest(arguments)

        # : :type response: SetBreakpointsResponse
        response = self.wait_for_response(self.write_request(request))
        body = response.body

        assert response.success == success

        if success:
            # : :type body: SetBreakpointsResponseBody
            assert len(body.breakpoints) == len(lines)
            lines_in_response = [b['line'] for b in body.breakpoints]

            if expected_lines_in_response is None:
                expected_lines_in_response = lines
            assert set(lines_in_response) == set(expected_lines_in_response)

            for b in body.breakpoints:
                assert b['verified'] == verified
        return response

    def write_set_exception_breakpoints(self, filters=None, exception_options=None):
        '''
        :param list(str) filters:
            A list with 'raised' or 'uncaught' entries.

        :param list(ExceptionOptions) exception_options:

        '''
        filters = filters or []
        assert set(filters).issubset(set(('raised', 'uncaught')))

        exception_options = exception_options or []
        exception_options = [exception_option.to_dict() for exception_option in exception_options]

        arguments = pydevd_schema.SetExceptionBreakpointsArguments(filters, exception_options)
        request = pydevd_schema.SetExceptionBreakpointsRequest(arguments)
        # : :type response: SetExceptionBreakpointsResponse
        response = self.wait_for_response(self.write_request(request))
        assert response.success

    def _write_launch_or_attach(self, command, **arguments):
        assert not self._sent_launch_or_attach
        self._sent_launch_or_attach = True
        arguments['noDebug'] = False
        request = {'type': 'request', 'command': command, 'arguments': arguments, 'seq':-1}
        self.wait_for_response(self.write_request(request))

    def write_launch(self, **arguments):
        return self._write_launch_or_attach('launch', **arguments)

    def write_attach(self, **arguments):
        return self._write_launch_or_attach('attach', **arguments)

    def write_disconnect(self, wait_for_response=True, terminate_debugee=False):
        assert self._sent_launch_or_attach
        self._sent_launch_or_attach = False
        arguments = pydevd_schema.DisconnectArguments(terminateDebuggee=terminate_debugee)
        request = pydevd_schema.DisconnectRequest(arguments=arguments)
        self.write_request(request)
        if wait_for_response:
            self.wait_for_response(request)

    def get_stack_as_json_hit(self, thread_id):
        stack_trace_request = self.write_request(
            pydevd_schema.StackTraceRequest(pydevd_schema.StackTraceArguments(threadId=thread_id)))

        # : :type stack_trace_response: StackTraceResponse
        # : :type stack_trace_response_body: StackTraceResponseBody
        # : :type stack_frame: StackFrame
        stack_trace_response = self.wait_for_response(stack_trace_request)
        stack_trace_response_body = stack_trace_response.body
        assert len(stack_trace_response_body.stackFrames) > 0

        for stack_frame in stack_trace_response_body.stackFrames:
            assert stack_frame['id'] < MAX_EXPECTED_ID

        stack_frame = next(iter(stack_trace_response_body.stackFrames))

        return _JsonHit(
            thread_id=thread_id, frame_id=stack_frame['id'], stack_trace_response=stack_trace_response)

    def get_variables_response(self, variables_reference, fmt=None, success=True):
        assert variables_reference < MAX_EXPECTED_ID
        variables_request = self.write_request(
            pydevd_schema.VariablesRequest(pydevd_schema.VariablesArguments(variables_reference, format=fmt)))
        variables_response = self.wait_for_response(variables_request)
        assert variables_response.success == success
        return variables_response

    def filter_return_variables(self, variables):
        ret = []
        for variable in variables:
            if variable['name'].startswith('(return)'):
                ret.append(variable)
        return ret

    def pop_variables_reference(self, lst):
        '''
        Modifies dicts in-place to remove the variablesReference and returns those (in the same order
        in which they were received).
        '''
        references = []
        for dct in lst:
            reference = dct.pop('variablesReference', None)
            if reference is not None:
                assert isinstance(reference, int_types)
                assert reference < MAX_EXPECTED_ID
            references.append(reference)
        return references

    def write_continue(self, wait_for_response=True):
        continue_request = self.write_request(
            pydevd_schema.ContinueRequest(pydevd_schema.ContinueArguments('*')))

        if wait_for_response:
            # The continued event is received before the response.
            assert self.wait_for_json_message(ContinuedEvent).body.allThreadsContinued

            continue_response = self.wait_for_response(continue_request)
            assert continue_response.body.allThreadsContinued

    def write_pause(self):
        pause_request = self.write_request(
            pydevd_schema.PauseRequest(pydevd_schema.PauseArguments('*')))
        pause_response = self.wait_for_response(pause_request)
        assert pause_response.success

    def write_step_in(self, thread_id):
        arguments = pydevd_schema.StepInArguments(threadId=thread_id)
        self.wait_for_response(self.write_request(pydevd_schema.StepInRequest(arguments)))

    def write_step_next(self, thread_id, wait_for_response=True):
        next_request = self.write_request(
            pydevd_schema.NextRequest(pydevd_schema.NextArguments(thread_id)))
        if wait_for_response:
            self.wait_for_response(next_request)

    def write_step_out(self, thread_id, wait_for_response=True):
        stepout_request = self.write_request(
            pydevd_schema.StepOutRequest(pydevd_schema.StepOutArguments(thread_id)))
        if wait_for_response:
            self.wait_for_response(stepout_request)

    def write_set_variable(self, frame_variables_reference, name, value, success=True):
        set_variable_request = self.write_request(
            pydevd_schema.SetVariableRequest(pydevd_schema.SetVariableArguments(
                frame_variables_reference, name, value,
        )))
        set_variable_response = self.wait_for_response(set_variable_request)
        if set_variable_response.success != success:
            raise AssertionError(
                'Expected %s. Found: %s\nResponse: %s\n' % (
                    success, set_variable_response.success, set_variable_response.to_json()))
        return set_variable_response

    def get_name_to_scope(self, frame_id):
        scopes_request = self.write_request(pydevd_schema.ScopesRequest(
            pydevd_schema.ScopesArguments(frame_id)))

        scopes_response = self.wait_for_response(scopes_request)

        scopes = scopes_response.body.scopes
        name_to_scopes = dict((scope['name'], pydevd_schema.Scope(**scope)) for scope in scopes)

        assert len(scopes) == 1
        assert sorted(name_to_scopes.keys()) == ['Locals']
        assert not name_to_scopes['Locals'].expensive

        return name_to_scopes

    def get_name_to_var(self, variables_reference):
        variables_response = self.get_variables_response(variables_reference)
        return dict((variable['name'], pydevd_schema.Variable(**variable)) for variable in variables_response.body.variables)

    def get_locals_name_to_var(self, frame_id):
        name_to_scope = self.get_name_to_scope(frame_id)

        return self.get_name_to_var(name_to_scope['Locals'].variablesReference)

    def get_local_var(self, frame_id, var_name):
        ret = self.get_locals_name_to_var(frame_id)[var_name]
        assert ret.name == var_name
        return ret

    def get_var(self, variables_reference, var_name=None, index=None):
        if var_name is not None:
            return self.get_name_to_var(variables_reference)[var_name]
        else:
            assert index is not None, 'Either var_name or index must be passed.'
            variables_response = self.get_variables_response(variables_reference)
            return pydevd_schema.Variable(**variables_response.body.variables[index])

    def write_set_debugger_property(
            self,
            dont_trace_start_patterns=None,
            dont_trace_end_patterns=None,
            multi_threads_single_notification=None,
            success=True
        ):
        dbg_request = self.write_request(
            pydevd_schema.SetDebuggerPropertyRequest(pydevd_schema.SetDebuggerPropertyArguments(
                dontTraceStartPatterns=dont_trace_start_patterns,
                dontTraceEndPatterns=dont_trace_end_patterns,
                multiThreadsSingleNotification=multi_threads_single_notification,
            )))
        response = self.wait_for_response(dbg_request)
        assert response.success == success
        return response

    def write_set_pydevd_source_map(self, source, pydevd_source_maps, success=True):
        dbg_request = self.write_request(
            pydevd_schema.SetPydevdSourceMapRequest(pydevd_schema.SetPydevdSourceMapArguments(
                source=source,
                pydevdSourceMaps=pydevd_source_maps,
            )))
        response = self.wait_for_response(dbg_request)
        assert response.success == success
        return response

    def write_initialize(self, success=True):
        arguments = InitializeRequestArguments(
            adapterID='pydevd_test_case',
        )
        response = self.wait_for_response(self.write_request(InitializeRequest(arguments)))
        assert response.success == success
        if success:
            process_id = response.body.kwargs['pydevd']['processId']
            assert isinstance(process_id, int)
        return response

    def write_authorize(self, access_token, success=True):
        from _pydevd_bundle._debug_adapter.pydevd_schema import PydevdAuthorizeArguments
        from _pydevd_bundle._debug_adapter.pydevd_schema import PydevdAuthorizeRequest
        arguments = PydevdAuthorizeArguments(
            debugServerAccessToken=access_token,
        )
        response = self.wait_for_response(self.write_request(PydevdAuthorizeRequest(arguments)))
        assert response.success == success
        return response

    def evaluate(self, expression, frameId=None, context=None, fmt=None, success=True):
        eval_request = self.write_request(
            pydevd_schema.EvaluateRequest(pydevd_schema.EvaluateArguments(
                expression, frameId=frameId, context=context, format=fmt)))
        eval_response = self.wait_for_response(eval_request)
        assert eval_response.success == success
        return eval_response

    def write_terminate(self):
        # Note: this currently terminates promptly, so, no answer is given.
        self.write_request(TerminateRequest(arguments=TerminateArguments()))


def test_case_json_logpoints(case_setup):
    with case_setup.test_file('_debugger_case_change_breaks.py') as writer:
        json_facade = JsonFacade(writer)

        json_facade.write_launch()
        break_2 = writer.get_line_index_with_content('break 2')
        break_3 = writer.get_line_index_with_content('break 3')
        json_facade.write_set_breakpoints(
            [break_2, break_3],
            line_to_info={
                break_2: {'log_message': 'var {repr("_a")} is {_a}'}
        })
        json_facade.write_make_initial_run()

        # Should only print, not stop on logpoints.
        messages = []
        while True:
            output_event = json_facade.wait_for_json_message(OutputEvent)
            msg = output_event.body.output
            ctx = output_event.body.category

            if ctx == 'stdout':
                msg = msg.strip()
                if msg == "var '_a' is 2":
                    messages.append(msg)

                if len(messages) == 2:
                    break

        # Just one hit at the end (break 3).
        json_facade.wait_for_thread_stopped(line=break_3)
        json_facade.write_continue()

        writer.finished_ok = True


def test_case_process_event(case_setup):
    with case_setup.test_file('_debugger_case_change_breaks.py') as writer:
        json_facade = JsonFacade(writer)

        json_facade.write_launch()
        assert len(json_facade.mark_messages(ProcessEvent)) == 1
        json_facade.write_make_initial_run()
        writer.finished_ok = True


def test_case_json_change_breaks(case_setup):
    with case_setup.test_file('_debugger_case_change_breaks.py') as writer:
        json_facade = JsonFacade(writer)

        break1_line = writer.get_line_index_with_content('break 1')
        # Note: we can only write breakpoints after the launch is received.
        json_facade.write_set_breakpoints(break1_line, success=False, send_launch_if_needed=False)

        json_facade.write_launch()
        json_facade.write_set_breakpoints(break1_line)
        json_facade.write_make_initial_run()

        json_facade.wait_for_thread_stopped(line=break1_line)
        json_facade.write_set_breakpoints([])
        json_facade.write_continue()

        writer.finished_ok = True


def test_case_handled_exception_breaks(case_setup):
    with case_setup.test_file('_debugger_case_exceptions.py') as writer:
        json_facade = JsonFacade(writer)

        json_facade.write_launch()
        json_facade.write_set_exception_breakpoints(['raised'])
        json_facade.write_make_initial_run()

        json_facade.wait_for_thread_stopped(
            reason='exception', line=writer.get_line_index_with_content('raise indexerror line'))
        json_facade.write_continue()

        json_facade.wait_for_thread_stopped(
            reason='exception', line=writer.get_line_index_with_content('reraise on method2'))

        # Clear so that the last one is not hit.
        json_facade.write_set_exception_breakpoints([])
        json_facade.write_continue()

        writer.finished_ok = True


@pytest.mark.parametrize('target_file', [
    '_debugger_case_unhandled_exceptions.py',
    '_debugger_case_unhandled_exceptions_custom.py',
    ])
def test_case_unhandled_exception(case_setup, target_file):

    def check_test_suceeded_msg(writer, stdout, stderr):
        # Don't call super (we have an unhandled exception in the stack trace).
        return 'TEST SUCEEDED' in ''.join(stdout) and 'TEST SUCEEDED' in ''.join(stderr)

    def additional_output_checks(writer, stdout, stderr):
        if 'raise MyError' not in stderr and 'raise Exception' not in stderr:
            raise AssertionError('Expected test to have an unhandled exception.\nstdout:\n%s\n\nstderr:\n%s' % (
                stdout, stderr))

    with case_setup.test_file(
            target_file,
            check_test_suceeded_msg=check_test_suceeded_msg,
            additional_output_checks=additional_output_checks,
            EXPECTED_RETURNCODE=1,
        ) as writer:
        json_facade = JsonFacade(writer)

        json_facade.write_launch()
        json_facade.write_set_exception_breakpoints(['uncaught'])
        json_facade.write_make_initial_run()

        line_in_thread1 = writer.get_line_index_with_content('in thread 1')
        line_in_thread2 = writer.get_line_index_with_content('in thread 2')
        line_in_main = writer.get_line_index_with_content('in main')
        json_facade.wait_for_thread_stopped(
            reason='exception', line=(line_in_thread1, line_in_thread2), file=target_file)
        json_facade.write_continue()

        json_facade.wait_for_thread_stopped(
            reason='exception', line=(line_in_thread1, line_in_thread2), file=target_file)
        json_facade.write_continue()

        json_facade.wait_for_thread_stopped(
            reason='exception', line=line_in_main, file=target_file)
        json_facade.write_continue()

        writer.finished_ok = True


@pytest.mark.parametrize('target_file', [
    '_debugger_case_unhandled_exceptions_generator.py',
    '_debugger_case_unhandled_exceptions_listcomp.py',
    ])
def test_case_unhandled_exception_generator(case_setup, target_file):

    def check_test_suceeded_msg(writer, stdout, stderr):
        # Don't call super (we have an unhandled exception in the stack trace).
        return 'TEST SUCEEDED' in ''.join(stdout) and 'TEST SUCEEDED' in ''.join(stderr)

    def additional_output_checks(writer, stdout, stderr):
        if 'ZeroDivisionError' not in stderr:
            raise AssertionError('Expected test to have an unhandled exception.\nstdout:\n%s\n\nstderr:\n%s' % (
                stdout, stderr))

    with case_setup.test_file(
            target_file,
            check_test_suceeded_msg=check_test_suceeded_msg,
            additional_output_checks=additional_output_checks,
            EXPECTED_RETURNCODE=1,
        ) as writer:
        json_facade = JsonFacade(writer)

        json_facade.write_launch()
        json_facade.write_set_exception_breakpoints(['uncaught'])
        json_facade.write_make_initial_run()

        line_in_main = writer.get_line_index_with_content('exc line')

        json_hit = json_facade.wait_for_thread_stopped(
            reason='exception', line=line_in_main, file=target_file)
        frames = json_hit.stack_trace_response.body.stackFrames
        json_facade.write_continue()

        if 'generator' in target_file:
            expected_frame_names = ['<genexpr>', 'f', '<module>']
        else:
            if IS_PY27 or IS_PY26:
                expected_frame_names = ['f', '<module>']
            else:
                expected_frame_names = ['<listcomp>', 'f', '<module>']

        frame_names = [f['name'] for f in frames]
        assert frame_names == expected_frame_names

        writer.finished_ok = True


def test_case_sys_exit_unhandled_exception(case_setup):

    with case_setup.test_file('_debugger_case_sysexit.py', EXPECTED_RETURNCODE=1) as writer:
        json_facade = JsonFacade(writer)
        json_facade.write_set_exception_breakpoints(['uncaught'])
        json_facade.write_make_initial_run()

        break_line = writer.get_line_index_with_content('sys.exit(1)')
        json_facade.wait_for_thread_stopped(
            reason='exception', line=break_line)
        json_facade.write_continue()

        writer.finished_ok = True


@pytest.mark.parametrize('break_on_system_exit_zero', [True, False])
def test_case_sys_exit_0_unhandled_exception(case_setup, break_on_system_exit_zero):

    with case_setup.test_file('_debugger_case_sysexit_0.py', EXPECTED_RETURNCODE=0) as writer:
        json_facade = JsonFacade(writer)
        json_facade.write_launch(
            debugOptions=['BreakOnSystemExitZero'] if break_on_system_exit_zero else [],
        )
        json_facade.write_set_exception_breakpoints(['uncaught'])
        json_facade.write_make_initial_run()

        break_line = writer.get_line_index_with_content('sys.exit(0)')
        if break_on_system_exit_zero:
            json_facade.wait_for_thread_stopped(
                reason='exception', line=break_line)
            json_facade.write_continue()

        writer.finished_ok = True


@pytest.mark.parametrize('break_on_system_exit_zero', [True, False])
def test_case_sys_exit_0_handled_exception(case_setup, break_on_system_exit_zero):

    with case_setup.test_file('_debugger_case_sysexit_0.py', EXPECTED_RETURNCODE=0) as writer:
        json_facade = JsonFacade(writer)
        json_facade.write_launch(
            debugOptions=['BreakOnSystemExitZero'] if break_on_system_exit_zero else [],
        )
        json_facade.write_set_exception_breakpoints(['raised'])
        json_facade.write_make_initial_run()

        break_line = writer.get_line_index_with_content('sys.exit(0)')
        break_main_line = writer.get_line_index_with_content('call_main_line')
        if break_on_system_exit_zero:
            json_facade.wait_for_thread_stopped(
                reason='exception', line=break_line)
            json_facade.write_continue()

            json_facade.wait_for_thread_stopped(
                reason='exception', line=break_main_line)
            json_facade.write_continue()

        writer.finished_ok = True


def test_case_handled_exception_breaks_by_type(case_setup):
    with case_setup.test_file('_debugger_case_exceptions.py') as writer:
        json_facade = JsonFacade(writer)

        json_facade.write_launch()
        json_facade.write_set_exception_breakpoints(exception_options=[
            ExceptionOptions(breakMode='always', path=[
                {'names': ['Python Exceptions']},
                {'names': ['IndexError']},
            ])
        ])
        json_facade.write_make_initial_run()

        json_facade.wait_for_thread_stopped(
            reason='exception', line=writer.get_line_index_with_content('raise indexerror line'))

        # Deal only with RuntimeErorr now.
        json_facade.write_set_exception_breakpoints(exception_options=[
            ExceptionOptions(breakMode='always', path=[
                {'names': ['Python Exceptions']},
                {'names': ['RuntimeError']},
            ])
        ])

        json_facade.write_continue()

        writer.finished_ok = True


def test_case_json_protocol(case_setup):
    with case_setup.test_file('_debugger_case_print.py') as writer:
        json_facade = JsonFacade(writer)

        json_facade.write_launch()
        break_line = writer.get_line_index_with_content('Break here')
        json_facade.write_set_breakpoints(break_line)
        json_facade.write_make_initial_run()

        json_facade.wait_for_json_message(ThreadEvent, lambda event: event.body.reason == 'started')

        json_facade.wait_for_thread_stopped(line=break_line)

        # : :type response: ThreadsResponse
        response = json_facade.write_list_threads()
        assert len(response.body.threads) == 1
        assert next(iter(response.body.threads))['name'] == 'MainThread'

        # Removes breakpoints and proceeds running.
        json_facade.write_disconnect()

        writer.finished_ok = True


def test_case_started_exited_threads_protocol(case_setup):
    with case_setup.test_file('_debugger_case_thread_started_exited.py') as writer:
        json_facade = JsonFacade(writer)

        json_facade.write_launch()
        break_line = writer.get_line_index_with_content('Break here')
        json_facade.write_set_breakpoints(break_line)

        json_facade.write_make_initial_run()

        _stopped_event = json_facade.wait_for_json_message(StoppedEvent)
        started_events = json_facade.mark_messages(ThreadEvent, lambda x: x.body.reason == 'started')
        exited_events = json_facade.mark_messages(ThreadEvent, lambda x: x.body.reason == 'exited')
        assert len(started_events) == 4
        assert len(exited_events) == 3  # Main is still running.
        json_facade.write_continue()

        writer.finished_ok = True


def test_case_path_translation_not_skipped(case_setup):
    import site
    sys_folder = None
    if hasattr(site, 'getusersitepackages'):
        sys_folder = site.getusersitepackages()

    if not sys_folder and hasattr(site, 'getsitepackages'):
        sys_folder = site.getsitepackages()

    if not sys_folder:
        sys_folder = sys.prefix

    if isinstance(sys_folder, (list, tuple)):
        sys_folder = next(iter(sys_folder))

    with case_setup.test_file('my_code/my_code.py') as writer:
        json_facade = JsonFacade(writer)

        # We need to set up path mapping to enable source references.
        my_code = debugger_unittest._get_debugger_test_file('my_code')

        json_facade.write_launch(
            debugOptions=['DebugStdLib'],
            pathMappings=[{
                'localRoot': sys_folder,
                'remoteRoot': my_code,
            }]
        )

        bp_line = writer.get_line_index_with_content('break here')
        json_facade.write_set_breakpoints(
            bp_line,
            filename=os.path.join(sys_folder, 'my_code.py'),
        )
        json_facade.write_make_initial_run()

        json_hit = json_facade.wait_for_thread_stopped(line=bp_line)

        assert json_hit.stack_trace_response.body.stackFrames[-1]['source']['path'] == \
            os.path.join(sys_folder, 'my_code.py')
        json_facade.write_continue()

        writer.finished_ok = True


@pytest.mark.parametrize("custom_setup", [
    'set_exclude_launch_module_full',
    'set_exclude_launch_module_prefix',
    'set_exclude_launch_path_match_filename',
    'set_exclude_launch_path_match_folder',
    'set_just_my_code',
    'set_just_my_code_and_include',
])
def test_case_skipping_filters(case_setup, custom_setup):
    with case_setup.test_file('my_code/my_code.py') as writer:
        json_facade = JsonFacade(writer)

        expect_just_my_code = False
        if custom_setup == 'set_exclude_launch_path_match_filename':
            json_facade.write_launch(
                debugOptions=['DebugStdLib'],
                rules=[
                    {'path': '**/other.py', 'include':False},
                ]
            )

        elif custom_setup == 'set_exclude_launch_path_match_folder':
            not_my_code_dir = debugger_unittest._get_debugger_test_file('not_my_code')
            json_facade.write_launch(
                debugOptions=['DebugStdLib'],
                rules=[
                    {'path': not_my_code_dir, 'include':False},
                ]
            )

            other_filename = os.path.join(not_my_code_dir, 'other.py')
            response = json_facade.write_set_breakpoints(1, filename=other_filename, verified=False)
            assert response.body.breakpoints == [
                {'verified': False, 'message': 'Breakpoint in file excluded by filters.', 'source': {'path': other_filename}, 'line': 1}]
            # Note: there's actually a use-case where we'd hit that breakpoint even if it was excluded
            # by filters, so, we must actually clear it afterwards (the use-case is that when we're
            # stepping into the context with the breakpoint we wouldn't skip it).
            json_facade.write_set_breakpoints([], filename=other_filename)

            other_filename = os.path.join(not_my_code_dir, 'file_that_does_not_exist.py')
            response = json_facade.write_set_breakpoints(1, filename=other_filename, verified=False)
            assert response.body.breakpoints == [
                {'verified': False, 'message': 'Breakpoint in file that does not exist.', 'source': {'path': other_filename}, 'line': 1}]

        elif custom_setup == 'set_exclude_launch_module_full':
            json_facade.write_launch(
                debugOptions=['DebugStdLib'],
                rules=[
                    {'module': 'not_my_code.other', 'include':False},
                ]
            )

        elif custom_setup == 'set_exclude_launch_module_prefix':
            json_facade.write_launch(
                debugOptions=['DebugStdLib'],
                rules=[
                    {'module': 'not_my_code', 'include':False},
                ]
            )

        elif custom_setup == 'set_just_my_code':
            expect_just_my_code = True
            writer.write_set_project_roots([debugger_unittest._get_debugger_test_file('my_code')])
            json_facade.write_launch(debugOptions=[])

            not_my_code_dir = debugger_unittest._get_debugger_test_file('not_my_code')
            other_filename = os.path.join(not_my_code_dir, 'other.py')
            response = json_facade.write_set_breakpoints(
                33, filename=other_filename, verified=False, expected_lines_in_response=[14])
            assert response.body.breakpoints == [{
                'verified': False,
                'message': 'Breakpoint in file excluded by filters.\nNote: may be excluded because of \"justMyCode\" option (default == true).Try setting \"justMyCode\": false in the debug configuration (e.g., launch.json).',
                'source': {'path': other_filename},
                'line': 14
            }]
        elif custom_setup == 'set_just_my_code_and_include':
            expect_just_my_code = True
            # I.e.: nothing in my_code (add it with rule).
            writer.write_set_project_roots([debugger_unittest._get_debugger_test_file('launch')])
            json_facade.write_launch(
                debugOptions=[],
                rules=[
                    {'module': '__main__', 'include':True},
                ]
            )

        else:
            raise AssertionError('Unhandled: %s' % (custom_setup,))

        break_line = writer.get_line_index_with_content('break here')
        json_facade.write_set_breakpoints(break_line)
        json_facade.write_make_initial_run()

        json_facade.wait_for_json_message(ThreadEvent, lambda event: event.body.reason == 'started')

        json_hit = json_facade.wait_for_thread_stopped(line=break_line)

        json_facade.write_step_in(json_hit.thread_id)

        json_hit = json_facade.wait_for_thread_stopped('step', name='callback1')

        messages = json_facade.mark_messages(
            OutputEvent, lambda output_event: 'Frame skipped from debugging during step-in.' in output_event.body.output)
        assert len(messages) == 1
        found_just_my_code = 'Note: may have been skipped because of \"justMyCode\" option (default == true)' in next(iter(messages)).body.output

        assert found_just_my_code == expect_just_my_code

        json_facade.write_step_in(json_hit.thread_id)
        json_hit = json_facade.wait_for_thread_stopped('step', name='callback2')

        json_facade.write_step_next(json_hit.thread_id)
        json_hit = json_facade.wait_for_thread_stopped('step', name='callback1')

        json_facade.write_step_next(json_hit.thread_id)
        json_hit = json_facade.wait_for_thread_stopped('step', name='<module>')

        json_facade.write_step_next(json_hit.thread_id)
        json_hit = json_facade.wait_for_thread_stopped('step', name='<module>')

        json_facade.write_step_next(json_hit.thread_id)

        if IS_JYTHON:
            json_facade.write_continue()

        # Check that it's sent only once.
        assert len(json_facade.mark_messages(
            OutputEvent, lambda output_event: 'Frame skipped from debugging during step-in.' in output_event.body.output)) == 0

        writer.finished_ok = True


def test_case_completions_json(case_setup):
    with case_setup.test_file('_debugger_case_completions.py') as writer:
        json_facade = JsonFacade(writer)

        writer.write_add_breakpoint(writer.get_line_index_with_content('Break here'))

        json_facade.write_make_initial_run()

        first_hit = None
        for i in range(2):
            json_hit = json_facade.wait_for_thread_stopped()

            json_hit = json_facade.get_stack_as_json_hit(json_hit.thread_id)
            if i == 0:
                first_hit = json_hit

            completions_arguments = pydevd_schema.CompletionsArguments(
                'dict.', 6, frameId=json_hit.frame_id, line=0)
            completions_request = json_facade.write_request(
                pydevd_schema.CompletionsRequest(completions_arguments))

            response = json_facade.wait_for_response(completions_request)
            assert response.success
            labels = [x['label'] for x in response.body.targets]
            assert set(labels).issuperset(set(['__contains__', 'items', 'keys', 'values']))

            completions_arguments = pydevd_schema.CompletionsArguments(
                'dict.item', 10, frameId=json_hit.frame_id)
            completions_request = json_facade.write_request(
                pydevd_schema.CompletionsRequest(completions_arguments))

            response = json_facade.wait_for_response(completions_request)
            assert response.success
            if IS_JYTHON:
                assert response.body.targets == [
                    {'start': 5, 'length': 4, 'type': 'keyword', 'label': 'items'}]
            else:
                assert response.body.targets == [
                    {'start': 5, 'length': 4, 'type': 'function', 'label': 'items'}]

            if i == 1:
                # Check with a previously existing frameId.
                assert first_hit.frame_id != json_hit.frame_id
                completions_arguments = pydevd_schema.CompletionsArguments(
                    'dict.item', 10, frameId=first_hit.frame_id)
                completions_request = json_facade.write_request(
                    pydevd_schema.CompletionsRequest(completions_arguments))

                response = json_facade.wait_for_response(completions_request)
                assert not response.success
                assert response.message == 'Thread to get completions seems to have resumed already.'

                # Check with a never frameId which never existed.
                completions_arguments = pydevd_schema.CompletionsArguments(
                    'dict.item', 10, frameId=99999)
                completions_request = json_facade.write_request(
                    pydevd_schema.CompletionsRequest(completions_arguments))

                response = json_facade.wait_for_response(completions_request)
                assert not response.success
                assert response.message.startswith('Wrong ID sent from the client:')

            json_facade.write_continue()

        writer.finished_ok = True


def test_modules(case_setup):
    with case_setup.test_file('_debugger_case_local_variables.py') as writer:
        json_facade = JsonFacade(writer)

        writer.write_add_breakpoint(writer.get_line_index_with_content('Break 2 here'))
        json_facade.write_make_initial_run()

        stopped_event = json_facade.wait_for_json_message(StoppedEvent)
        thread_id = stopped_event.body.threadId

        json_facade.write_request(
            pydevd_schema.StackTraceRequest(pydevd_schema.StackTraceArguments(threadId=thread_id)))

        json_facade.wait_for_json_message(ModuleEvent)

        # : :type response: ModulesResponse
        # : :type modules_response_body: ModulesResponseBody
        response = json_facade.wait_for_response(json_facade.write_request(
            pydevd_schema.ModulesRequest(pydevd_schema.ModulesArguments())))
        modules_response_body = response.body
        assert len(modules_response_body.modules) == 1
        module = next(iter(modules_response_body.modules))
        assert module['name'] == '__main__'
        assert module['path'].endswith('_debugger_case_local_variables.py')

        json_facade.write_continue()
        writer.finished_ok = True


@pytest.mark.skipif(IS_JYTHON, reason='Putting unicode on frame vars does not work on Jython.')
def test_stack_and_variables_dict(case_setup):
    with case_setup.test_file('_debugger_case_local_variables.py') as writer:
        json_facade = JsonFacade(writer)

        writer.write_add_breakpoint(writer.get_line_index_with_content('Break 2 here'))
        json_facade.write_make_initial_run()

        json_hit = json_facade.wait_for_thread_stopped()
        json_hit = json_facade.get_stack_as_json_hit(json_hit.thread_id)

        variables_response = json_facade.get_variables_response(json_hit.frame_id)

        variables_references = json_facade.pop_variables_reference(variables_response.body.variables)
        dict_variable_reference = variables_references[2]
        assert isinstance(dict_variable_reference, int_types)
        # : :type variables_response: VariablesResponse

        if IS_PY2:
            print(repr(variables_response.body.variables[-1]))
            expected_unicode = {
                u'name': u'\u16a0',
                u'value': u"u'\\u16a1'",
                u'type': u'unicode',
                u'presentationHint': {u'attributes': [u'rawString']},
                u'evaluateName': u'\u16a0',
            }
        else:
            expected_unicode = {
                'name': u'\u16A0',
                'value': "'\u16a1'",
                'type': 'str',
                'presentationHint': {'attributes': ['rawString']},
                'evaluateName': u'\u16A0',
            }
        assert variables_response.body.variables == [
            {'name': 'variable_for_test_1', 'value': '10', 'type': 'int', 'evaluateName': 'variable_for_test_1'},
            {'name': 'variable_for_test_2', 'value': '20', 'type': 'int', 'evaluateName': 'variable_for_test_2'},
            {'name': 'variable_for_test_3', 'value': "{'a': 30, 'b': 20}", 'type': 'dict', 'evaluateName': 'variable_for_test_3'},
            expected_unicode
        ]

        variables_response = json_facade.get_variables_response(dict_variable_reference)
        assert variables_response.body.variables == [
            {'name': "'a'", 'value': '30', 'type': 'int', 'evaluateName': "variable_for_test_3['a']", 'variablesReference': 0 },
            {'name': "'b'", 'value': '20', 'type': 'int', 'evaluateName': "variable_for_test_3['b']", 'variablesReference': 0},
            {'name': '__len__', 'value': '2', 'type': 'int', 'evaluateName': 'len(variable_for_test_3)', 'variablesReference': 0, 'presentationHint': {'attributes': ['readOnly']}}
        ]

        json_facade.write_continue()
        writer.finished_ok = True


def test_return_value(case_setup):
    with case_setup.test_file('_debugger_case_return_value.py') as writer:
        json_facade = JsonFacade(writer)

        break_line = writer.get_line_index_with_content('break here')
        json_facade.write_launch(debugOptions=['ShowReturnValue'])
        json_facade.write_set_breakpoints(break_line)
        json_facade.write_make_initial_run()

        json_hit = json_facade.wait_for_thread_stopped()
        json_facade.write_step_next(json_hit.thread_id)
        json_hit = json_facade.wait_for_thread_stopped('step', name='<module>', line=break_line + 1)

        variables_response = json_facade.get_variables_response(json_hit.frame_id)
        return_variables = json_facade.filter_return_variables(variables_response.body.variables)
        assert return_variables == [{
            'name': '(return) method1',
            'value': '1',
            'type': 'int',
            'evaluateName': "__pydevd_ret_val_dict['method1']",
            'presentationHint': {'attributes': ['readOnly']},
            'variablesReference': 0,
        }]

        json_facade.write_continue()
        writer.finished_ok = True


def test_stack_and_variables_set_and_list(case_setup):
    with case_setup.test_file('_debugger_case_local_variables2.py') as writer:
        json_facade = JsonFacade(writer)

        writer.write_add_breakpoint(writer.get_line_index_with_content('Break here'))
        json_facade.write_make_initial_run()

        json_hit = json_facade.wait_for_thread_stopped()
        json_hit = json_facade.get_stack_as_json_hit(json_hit.thread_id)
        variables_response = json_facade.get_variables_response(json_hit.frame_id)

        variables_references = json_facade.pop_variables_reference(variables_response.body.variables)
        if IS_PY2:
            expected_set = "set(['a'])"
        else:
            expected_set = "{'a'}"
        assert variables_response.body.variables == [
            {'type': 'list', 'evaluateName': 'variable_for_test_1', 'name': 'variable_for_test_1', 'value': "['a', 'b']"},
            {'type': 'set', 'evaluateName': 'variable_for_test_2', 'name': 'variable_for_test_2', 'value': expected_set}
        ]

        variables_response = json_facade.get_variables_response(variables_references[0])
        assert variables_response.body.variables == [{
            u'name': u'0',
            u'type': u'str',
            u'value': u"'a'",
            u'presentationHint': {u'attributes': [u'rawString']},
            u'evaluateName': u'variable_for_test_1[0]',
            u'variablesReference': 0,
        },
        {
            u'name': u'1',
            u'type': u'str',
            u'value': u"'b'",
            u'presentationHint': {u'attributes': [u'rawString']},
            u'evaluateName': u'variable_for_test_1[1]',
            u'variablesReference': 0,
        },
        {
            u'name': u'__len__',
            u'type': u'int',
            u'value': u'2',
            u'evaluateName': u'len(variable_for_test_1)',
            u'variablesReference': 0,
            u'presentationHint': {'attributes': ['readOnly']},
        }]

        json_facade.write_continue()
        writer.finished_ok = True


@pytest.mark.skipif(IS_JYTHON, reason='Putting unicode on frame vars does not work on Jython.')
def test_evaluate_unicode(case_setup):
    from _pydevd_bundle._debug_adapter.pydevd_schema import EvaluateRequest
    from _pydevd_bundle._debug_adapter.pydevd_schema import EvaluateArguments
    with case_setup.test_file('_debugger_case_local_variables.py') as writer:
        json_facade = JsonFacade(writer)

        writer.write_add_breakpoint(writer.get_line_index_with_content('Break 2 here'))
        json_facade.write_make_initial_run()

        json_hit = json_facade.wait_for_thread_stopped()
        json_hit = json_facade.get_stack_as_json_hit(json_hit.thread_id)

        evaluate_response = json_facade.wait_for_response(
            json_facade.write_request(EvaluateRequest(EvaluateArguments(u'\u16A0', json_hit.frame_id))))

        evaluate_response_body = evaluate_response.body.to_dict()

        if IS_PY2:
            # The error can be referenced.
            variables_reference = json_facade.pop_variables_reference([evaluate_response_body])

            assert evaluate_response_body == {
                'result': u"SyntaxError('invalid syntax', ('<string>', 1, 1, '\\xe1\\x9a\\xa0'))",
                'type': u'SyntaxError',
                'presentationHint': {},
            }

            assert len(variables_reference) == 1
            reference = variables_reference[0]
            assert reference > 0
            variables_response = json_facade.get_variables_response(reference)
            child_variables = variables_response.to_dict()['body']['variables']
            assert len(child_variables) == 1
            assert json_facade.pop_variables_reference(child_variables)[0] > 0
            assert child_variables == [{
                u'type': u'SyntaxError',
                u'evaluateName': u'\u16a0.result',
                u'name': u'result',
                u'value': u"SyntaxError('invalid syntax', ('<string>', 1, 1, '\\xe1\\x9a\\xa0'))"
            }]

        else:
            assert evaluate_response_body == {
                'result': "'\u16a1'",
                'type': 'str',
                'variablesReference': 0,
                'presentationHint': {'attributes': ['rawString']},
            }

        json_facade.write_continue()
        writer.finished_ok = True


def test_evaluate_variable_references(case_setup):
    from _pydevd_bundle._debug_adapter.pydevd_schema import EvaluateRequest
    from _pydevd_bundle._debug_adapter.pydevd_schema import EvaluateArguments
    with case_setup.test_file('_debugger_case_local_variables2.py') as writer:
        json_facade = JsonFacade(writer)

        writer.write_add_breakpoint(writer.get_line_index_with_content('Break here'))
        json_facade.write_make_initial_run()

        json_hit = json_facade.wait_for_thread_stopped()
        json_hit = json_facade.get_stack_as_json_hit(json_hit.thread_id)

        evaluate_response = json_facade.wait_for_response(
            json_facade.write_request(EvaluateRequest(EvaluateArguments('variable_for_test_2', json_hit.frame_id))))

        evaluate_response_body = evaluate_response.body.to_dict()

        variables_reference = json_facade.pop_variables_reference([evaluate_response_body])

        assert evaluate_response_body == {
            'type': 'set',
            'result': "set(['a'])" if IS_PY2 else "{'a'}",
            'presentationHint': {},
        }
        assert len(variables_reference) == 1
        reference = variables_reference[0]
        assert reference > 0
        variables_response = json_facade.get_variables_response(reference)
        child_variables = variables_response.to_dict()['body']['variables']

        # The name for a reference in a set is the id() of the variable and can change at each run.
        del child_variables[0]['name']

        assert child_variables == [
            {
                'type': 'str',
                'value': "'a'",
                'presentationHint': {'attributes': ['rawString']},
                'variablesReference': 0,
            },
            {
                'name': '__len__',
                'type': 'int',
                'value': '1',
                'presentationHint': {'attributes': ['readOnly']},
                'evaluateName': 'len(variable_for_test_2)',
                'variablesReference': 0,
            }
        ]

        json_facade.write_continue()
        writer.finished_ok = True


def test_set_expression(case_setup):
    from _pydevd_bundle._debug_adapter.pydevd_schema import SetExpressionRequest
    from _pydevd_bundle._debug_adapter.pydevd_schema import SetExpressionArguments
    with case_setup.test_file('_debugger_case_local_variables2.py') as writer:
        json_facade = JsonFacade(writer)

        writer.write_add_breakpoint(writer.get_line_index_with_content('Break here'))
        json_facade.write_make_initial_run()

        json_hit = json_facade.wait_for_thread_stopped()
        json_hit = json_facade.get_stack_as_json_hit(json_hit.thread_id)

        set_expression_response = json_facade.wait_for_response(
            json_facade.write_request(SetExpressionRequest(
                SetExpressionArguments('bb', '20', frameId=json_hit.frame_id))))
        assert set_expression_response.to_dict()['body'] == {
            'value': '20', 'type': 'int', 'presentationHint': {}, 'variablesReference': 0}

        variables_response = json_facade.get_variables_response(json_hit.frame_id)
        assert {'name': 'bb', 'value': '20', 'type': 'int', 'evaluateName': 'bb', 'variablesReference': 0} in \
            variables_response.to_dict()['body']['variables']

        json_facade.write_continue()
        writer.finished_ok = True


def test_set_expression_failures(case_setup):
    from _pydevd_bundle._debug_adapter.pydevd_schema import SetExpressionRequest
    from _pydevd_bundle._debug_adapter.pydevd_schema import SetExpressionArguments

    with case_setup.test_file('_debugger_case_local_variables2.py') as writer:
        json_facade = JsonFacade(writer)

        json_facade.write_set_breakpoints(writer.get_line_index_with_content('Break here'))

        json_facade.write_make_initial_run()

        json_hit = json_facade.wait_for_thread_stopped()
        json_hit = json_facade.get_stack_as_json_hit(json_hit.thread_id)

        set_expression_response = json_facade.wait_for_response(
            json_facade.write_request(SetExpressionRequest(
                SetExpressionArguments('frame_not_there', '10', frameId=0))))
        assert not set_expression_response.success
        assert set_expression_response.message == 'Unable to find thread to set expression.'

        json_facade.write_continue()

        writer.finished_ok = True


def test_get_variable_errors(case_setup):
    with case_setup.test_file('_debugger_case_completions.py') as writer:
        json_facade = JsonFacade(writer)

        json_facade.write_set_breakpoints(writer.get_line_index_with_content('Break here'))
        json_facade.write_make_initial_run()

        json_hit = json_facade.wait_for_thread_stopped()

        # First, try with wrong id.
        response = json_facade.get_variables_response(9999, success=False)
        assert response.message == 'Wrong ID sent from the client: 9999'

        first_hit = None
        for i in range(2):
            json_hit = json_facade.get_stack_as_json_hit(json_hit.thread_id)
            if i == 0:
                first_hit = json_hit

            if i == 1:
                # Now, check with a previously existing frameId.
                response = json_facade.get_variables_response(first_hit.frame_id, success=False)
                assert response.message == 'Unable to find thread to evaluate variable reference.'

            json_facade.write_continue(wait_for_response=i == 0)
            if i == 0:
                json_hit = json_facade.wait_for_thread_stopped()

        writer.finished_ok = True


def test_set_variable_failure(case_setup):
    with case_setup.test_file('_debugger_case_local_variables2.py') as writer:
        json_facade = JsonFacade(writer)

        json_facade.write_set_breakpoints(writer.get_line_index_with_content('Break here'))

        json_facade.write_make_initial_run()

        json_facade.wait_for_thread_stopped()

        # Wrong frame
        set_variable_response = json_facade.write_set_variable(0, 'invalid_reference', 'invalid_reference', success=False)
        assert not set_variable_response.success
        assert set_variable_response.message == 'Unable to find thread to evaluate variable reference.'

        json_facade.write_continue()

        writer.finished_ok = True


def _check_list(json_facade, json_hit):

    variable = json_facade.get_local_var(json_hit.frame_id, 'variable_for_test_1')
    assert variable.value == "['a', 'b', self.var1: 11]"

    var0 = json_facade.get_var(variable.variablesReference, '0')

    json_facade.write_set_variable(variable.variablesReference, var0.name, '1')

    # Check that it was actually changed.
    variable = json_facade.get_local_var(json_hit.frame_id, 'variable_for_test_1')
    assert variable.value == "[1, 'b', self.var1: 11]"

    var1 = json_facade.get_var(variable.variablesReference, 'var1')

    json_facade.write_set_variable(variable.variablesReference, var1.name, '2')

    variable = json_facade.get_local_var(json_hit.frame_id, 'variable_for_test_1')
    assert variable.value == "[1, 'b', self.var1: 2]"


def _check_tuple(json_facade, json_hit):

    variable = json_facade.get_local_var(json_hit.frame_id, 'variable_for_test_4')
    assert variable.value == "tuple('a', 1, self.var1: 13)"

    var0 = json_facade.get_var(variable.variablesReference, '0')

    response = json_facade.write_set_variable(variable.variablesReference, var0.name, '1', success=False)
    assert response.message.startswith("Unable to change: ")

    var1 = json_facade.get_var(variable.variablesReference, 'var1')
    json_facade.write_set_variable(variable.variablesReference, var1.name, '2')

    variable = json_facade.get_local_var(json_hit.frame_id, 'variable_for_test_4')
    assert variable.value == "tuple('a', 1, self.var1: 2)"


def _check_dict_subclass(json_facade, json_hit):
    variable = json_facade.get_local_var(json_hit.frame_id, 'variable_for_test_3')
    assert variable.value == "{in_dct: 20; self.var1: 10}"

    var1 = json_facade.get_var(variable.variablesReference, 'var1')

    json_facade.write_set_variable(variable.variablesReference, var1.name, '2')

    # Check that it was actually changed.
    variable = json_facade.get_local_var(json_hit.frame_id, 'variable_for_test_3')
    assert variable.value == "{in_dct: 20; self.var1: 2}"

    var_in_dct = json_facade.get_var(variable.variablesReference, "'in_dct'")

    json_facade.write_set_variable(variable.variablesReference, var_in_dct.name, '5')

    # Check that it was actually changed.
    variable = json_facade.get_local_var(json_hit.frame_id, 'variable_for_test_3')
    assert variable.value == "{in_dct: 5; self.var1: 2}"


def _check_set(json_facade, json_hit):
    set_var = json_facade.get_local_var(json_hit.frame_id, 'variable_for_test_2')

    assert set_var.value == "set(['a', self.var1: 12])"

    var_in_set = json_facade.get_var(set_var.variablesReference, index=1)
    assert var_in_set.name != 'var1'

    set_variables_response = json_facade.write_set_variable(set_var.variablesReference, var_in_set.name, '1')
    assert set_variables_response.body.type == "int"
    assert set_variables_response.body.value == "1"

    # Check that it was actually changed (which for a set means removing the existing entry
    # and adding a new one).
    set_var = json_facade.get_local_var(json_hit.frame_id, 'variable_for_test_2')
    assert set_var.value == "set([1, self.var1: 12])"

    # Check that it can be changed again.
    var_in_set = json_facade.get_var(set_var.variablesReference, index=1)

    # Check that adding a mutable object to the set does not work.
    response = json_facade.write_set_variable(set_var.variablesReference, var_in_set.name, '[22]', success=False)
    assert response.message.startswith('Unable to change: ')

    # Check that it's still the same (the existing entry was not removed).
    assert json_facade.get_local_var(json_hit.frame_id, 'variable_for_test_2').value == "set([1, self.var1: 12])"

    set_variables_response = json_facade.write_set_variable(set_var.variablesReference, var_in_set.name, '(22,)')
    assert set_variables_response.body.type == "tuple"
    assert set_variables_response.body.value == "(22,)"

    # Check that the tuple created can be accessed and is correct in the response.
    var_in_tuple_in_set = json_facade.get_var(set_variables_response.body.variablesReference, '0')
    assert var_in_tuple_in_set.name == '0'
    assert var_in_tuple_in_set.value == '22'

    # Check that we can change the variable in the instance.
    var1 = json_facade.get_var(set_var.variablesReference, 'var1')

    json_facade.write_set_variable(set_var.variablesReference, var1.name, '2')

    # Check that it was actually changed.
    set_var = json_facade.get_local_var(json_hit.frame_id, 'variable_for_test_2')
    assert set_var.value == "set([(22,), self.var1: 2])"


@pytest.mark.parametrize('_check_func', [
    _check_tuple,
    _check_set,
    _check_list,
    _check_dict_subclass,
])
def test_set_variable_multiple_cases(case_setup, _check_func):
    with case_setup.test_file('_debugger_case_local_variables3.py') as writer:
        json_facade = JsonFacade(writer)

        json_facade.write_set_breakpoints(writer.get_line_index_with_content('Break here'))

        json_facade.write_make_initial_run()

        json_hit = json_facade.wait_for_thread_stopped()

        _check_func(json_facade, json_hit)

        json_facade.write_continue()

        writer.finished_ok = True


@pytest.mark.skipif(IS_JYTHON, reason='Putting unicode on frame vars does not work on Jython.')
def test_stack_and_variables(case_setup):

    with case_setup.test_file('_debugger_case_local_variables.py') as writer:
        json_facade = JsonFacade(writer)

        json_facade.write_set_breakpoints(writer.get_line_index_with_content('Break here'))

        json_facade.write_make_initial_run()

        json_hit = json_facade.wait_for_thread_stopped()

        # : :type stack_trace_response: StackTraceResponse
        # : :type stack_trace_response_body: StackTraceResponseBody
        # : :type stack_frame: StackFrame

        # Check stack trace format.
        stack_trace_request = json_facade.write_request(
            pydevd_schema.StackTraceRequest(pydevd_schema.StackTraceArguments(
                threadId=json_hit.thread_id,
                format={'module': True, 'line': True}
        )))
        stack_trace_response = json_facade.wait_for_response(stack_trace_request)
        stack_trace_response_body = stack_trace_response.body
        stack_frame = next(iter(stack_trace_response_body.stackFrames))
        assert stack_frame['name'] == '__main__.Call : 4'

        # Regular stack trace request (no format).
        json_hit = json_facade.get_stack_as_json_hit(json_hit.thread_id)
        stack_trace_response = json_hit.stack_trace_response
        stack_trace_response_body = stack_trace_response.body
        assert len(stack_trace_response_body.stackFrames) == 2
        stack_frame = next(iter(stack_trace_response_body.stackFrames))
        assert stack_frame['name'] == 'Call'
        assert stack_frame['source']['path'].endswith('_debugger_case_local_variables.py')

        name_to_scope = json_facade.get_name_to_scope(stack_frame['id'])
        scope = name_to_scope['Locals']
        frame_variables_reference = scope.variablesReference
        assert isinstance(frame_variables_reference, int)

        variables_response = json_facade.get_variables_response(frame_variables_reference)
        # : :type variables_response: VariablesResponse
        assert len(variables_response.body.variables) == 0  # No variables expected here

        json_facade.write_step_next(json_hit.thread_id)
        json_hit = json_facade.wait_for_thread_stopped('step')

        variables_response = json_facade.get_variables_response(frame_variables_reference)
        # : :type variables_response: VariablesResponse
        assert variables_response.body.variables == [{
            'name': 'variable_for_test_1',
            'value': '10',
            'type': 'int',
            'evaluateName': 'variable_for_test_1',
            'variablesReference': 0,
        }]

        # Same thing with hex format
        variables_response = json_facade.get_variables_response(frame_variables_reference, fmt={'hex': True})
        # : :type variables_response: VariablesResponse
        assert variables_response.body.variables == [{
            'name': 'variable_for_test_1',
            'value': '0xa',
            'type': 'int',
            'evaluateName': 'variable_for_test_1',
            'variablesReference': 0,
        }]

        # Note: besides the scope/stack/variables we can also have references when:
        # - setting variable
        #    * If the variable was changed to a container, the new reference should be returned.
        # - evaluate expression
        #    * Currently ptvsd returns a None value in on_setExpression, so, skip this for now.
        # - output
        #    * Currently not handled by ptvsd, so, skip for now.

        # Reference is for parent (in this case the frame).
        # We'll change `variable_for_test_1` from 10 to [1].
        set_variable_response = json_facade.write_set_variable(
            frame_variables_reference, 'variable_for_test_1', '[1]')
        set_variable_response_as_dict = set_variable_response.to_dict()['body']
        if not IS_JYTHON:
            # Not properly changing var on Jython.
            assert isinstance(set_variable_response_as_dict.pop('variablesReference'), int)
            assert set_variable_response_as_dict == {'value': "[1]", 'type': 'list'}

        variables_response = json_facade.get_variables_response(frame_variables_reference)
        # : :type variables_response: VariablesResponse
        variables = variables_response.body.variables
        assert len(variables) == 1
        var_as_dict = next(iter(variables))
        if not IS_JYTHON:
            # Not properly changing var on Jython.
            assert isinstance(var_as_dict.pop('variablesReference'), int)
            assert var_as_dict == {
                'name': 'variable_for_test_1',
                'value': "[1]",
                'type': 'list',
                'evaluateName': 'variable_for_test_1',
            }

        json_facade.write_continue()

        writer.finished_ok = True


def test_hex_variables(case_setup):
    with case_setup.test_file('_debugger_case_local_variables_hex.py') as writer:
        json_facade = JsonFacade(writer)

        writer.write_add_breakpoint(writer.get_line_index_with_content('Break here'))

        json_facade.write_make_initial_run()

        json_hit = json_facade.wait_for_thread_stopped()

        # : :type stack_trace_response: StackTraceResponse
        # : :type stack_trace_response_body: StackTraceResponseBody
        # : :type stack_frame: StackFrame
        stack_trace_request = json_facade.write_request(
            pydevd_schema.StackTraceRequest(pydevd_schema.StackTraceArguments(threadId=json_hit.thread_id)))
        stack_trace_response = json_facade.wait_for_response(stack_trace_request)
        stack_trace_response_body = stack_trace_response.body
        assert len(stack_trace_response_body.stackFrames) == 2
        stack_frame = next(iter(stack_trace_response_body.stackFrames))
        assert stack_frame['name'] == 'Call'
        assert stack_frame['source']['path'].endswith('_debugger_case_local_variables_hex.py')

        name_to_scope = json_facade.get_name_to_scope(stack_frame['id'])

        scope = name_to_scope['Locals']
        frame_variables_reference = scope.variablesReference
        assert isinstance(frame_variables_reference, int)

        fmt = {'hex': True}
        variables_request = json_facade.write_request(
            pydevd_schema.VariablesRequest(pydevd_schema.VariablesArguments(frame_variables_reference, format=fmt)))
        variables_response = json_facade.wait_for_response(variables_request)

        # : :type variables_response: VariablesResponse
        variable_for_test_1, variable_for_test_2, variable_for_test_3, variable_for_test_4 = sorted(list(
            v for v in variables_response.body.variables if v['name'].startswith('variables_for_test')
        ), key=lambda v: v['name'])
        assert variable_for_test_1 == {
            'name': 'variables_for_test_1',
            'value': "0x64",
            'type': 'int',
            'evaluateName': 'variables_for_test_1',
            'variablesReference': 0,
        }

        assert isinstance(variable_for_test_2.pop('variablesReference'), int)
        assert variable_for_test_2 == {
            'name': 'variables_for_test_2',
            'value': "[0x1, 0xa, 0x64]",
            'type': 'list',
            'evaluateName': 'variables_for_test_2'
        }

        assert isinstance(variable_for_test_3.pop('variablesReference'), int)
        assert variable_for_test_3 == {
            'name': 'variables_for_test_3',
            'value': '{0xa: 0xa, 0x64: 0x64, 0x3e8: 0x3e8}',
            'type': 'dict',
            'evaluateName': 'variables_for_test_3'
        }

        assert isinstance(variable_for_test_4.pop('variablesReference'), int)
        assert variable_for_test_4 == {
            'name': 'variables_for_test_4',
            'value': '{(0x1, 0xa, 0x64): (0x2710, 0x186a0, 0x186a0)}',
            'type': 'dict',
            'evaluateName': 'variables_for_test_4'
        }

        json_facade.write_continue()

        writer.finished_ok = True


def test_stopped_event(case_setup):
    with case_setup.test_file('_debugger_case_print.py') as writer:
        json_facade = JsonFacade(writer)

        writer.write_add_breakpoint(writer.get_line_index_with_content('Break here'))

        json_facade.write_make_initial_run()

        json_hit = json_facade.wait_for_thread_stopped()
        assert json_hit.thread_id

        json_facade.write_continue()

        writer.finished_ok = True


@pytest.mark.skipif(IS_JYTHON, reason='Not Jython compatible (fails on set variable).')
def test_pause_and_continue(case_setup):
    with case_setup.test_file('_debugger_case_pause_continue.py') as writer:
        json_facade = JsonFacade(writer)

        json_facade.write_set_breakpoints(writer.get_line_index_with_content('Break here'))

        json_facade.write_make_initial_run()

        json_facade.wait_for_thread_stopped()

        json_facade.write_continue()

        json_facade.write_pause()

        json_hit = json_facade.wait_for_thread_stopped(reason="pause")

        stack_frame = next(iter(json_hit.stack_trace_response.body.stackFrames))

        name_to_scope = json_facade.get_name_to_scope(stack_frame['id'])
        frame_variables_reference = name_to_scope['Locals'].variablesReference

        set_variable_response = json_facade.write_set_variable(frame_variables_reference, 'loop', 'False')
        set_variable_response_as_dict = set_variable_response.to_dict()['body']
        assert set_variable_response_as_dict == {'value': "False", 'type': 'bool', 'variablesReference': 0}

        json_facade.write_continue()

        writer.finished_ok = True


@pytest.mark.parametrize('stepping_resumes_all_threads', [False, True])
def test_step_out_multi_threads(case_setup, stepping_resumes_all_threads):
    with case_setup.test_file('_debugger_case_multi_threads_stepping.py') as writer:
        json_facade = JsonFacade(writer)

        json_facade.write_launch(steppingResumesAllThreads=stepping_resumes_all_threads)
        json_facade.write_set_breakpoints([
            writer.get_line_index_with_content('Break thread 1'),
        ])
        json_facade.write_make_initial_run()

        json_hit = json_facade.wait_for_thread_stopped()

        response = json_facade.write_list_threads()
        assert len(response.body.threads) == 3

        thread_name_to_id = dict((t['name'], t['id']) for t in response.body.threads)
        assert json_hit.thread_id == thread_name_to_id['thread1']

        if stepping_resumes_all_threads:
            # If we're stepping with multiple threads, we'll exit here.
            json_facade.write_step_out(thread_name_to_id['thread1'])
        else:
            json_facade.write_step_out(thread_name_to_id['thread1'])

            # Timeout is expected... make it shorter.
            writer.reader_thread.set_messages_timeout(2)
            try:
                json_hit = json_facade.wait_for_thread_stopped('step')
                raise AssertionError('Expected timeout!')
            except debugger_unittest.TimeoutError:
                pass

            json_facade.write_step_out(thread_name_to_id['thread2'])
            json_facade.write_step_next(thread_name_to_id['MainThread'])
            json_hit = json_facade.wait_for_thread_stopped('step')
            assert json_hit.thread_id == thread_name_to_id['MainThread']
            json_facade.write_continue()

        writer.finished_ok = True


@pytest.mark.parametrize('stepping_resumes_all_threads', [True, False])
@pytest.mark.parametrize('step_mode', ['step_next', 'step_in'])
def test_step_next_step_in_multi_threads(case_setup, stepping_resumes_all_threads, step_mode):
    with case_setup.test_file('_debugger_case_multi_threads_stepping.py') as writer:
        json_facade = JsonFacade(writer)

        json_facade.write_launch(steppingResumesAllThreads=stepping_resumes_all_threads)
        json_facade.write_set_breakpoints([
            writer.get_line_index_with_content('Break thread 1'),
        ])
        json_facade.write_make_initial_run()

        json_hit = json_facade.wait_for_thread_stopped()

        response = json_facade.write_list_threads()
        assert len(response.body.threads) == 3

        thread_name_to_id = dict((t['name'], t['id']) for t in response.body.threads)
        assert json_hit.thread_id == thread_name_to_id['thread1']

        for _i in range(20):
            if step_mode == 'step_next':
                json_facade.write_step_next(thread_name_to_id['thread1'])

            elif step_mode == 'step_in':
                json_facade.write_step_in(thread_name_to_id['thread1'])

            else:
                raise AssertionError('Unexpected step_mode: %s' % (step_mode,))

            json_hit = json_facade.wait_for_thread_stopped('step')
            assert json_hit.thread_id == thread_name_to_id['thread1']
            local_var = json_facade.get_local_var(json_hit.frame_id, '_event2_set')

            # We're stepping in a single thread which depends on events being set in
            # another thread, so, we can only get here if the other thread was also released.
            if local_var.value == 'True':
                if stepping_resumes_all_threads:
                    break
                else:
                    raise AssertionError('Did not expect _event2_set to be set when not resuming other threads on step.')

            time.sleep(.01)
        else:
            if stepping_resumes_all_threads:
                raise AssertionError('Expected _event2_set to be set already.')
            else:
                # That's correct, we should never reach the condition where _event2_set is set if
                # we're not resuming other threads on step.
                pass

        json_facade.write_continue()

        writer.finished_ok = True


def test_stepping(case_setup):
    with case_setup.test_file('_debugger_case_stepping.py') as writer:
        json_facade = JsonFacade(writer)

        json_facade.write_launch(debugOptions=['DebugStdLib'])
        json_facade.write_set_breakpoints([
            writer.get_line_index_with_content('Break here 1'),
            writer.get_line_index_with_content('Break here 2')
        ])
        json_facade.write_make_initial_run()

        json_hit = json_facade.wait_for_thread_stopped()

        # Test Step-Over or 'next'
        stack_trace_response = json_hit.stack_trace_response
        stack_frame = next(iter(stack_trace_response.body.stackFrames))
        before_step_over_line = stack_frame['line']

        json_facade.write_step_next(json_hit.thread_id)
        json_hit = json_facade.wait_for_thread_stopped('step', line=before_step_over_line + 1)

        # Test step into or 'stepIn'
        json_facade.write_step_in(json_hit.thread_id)
        json_hit = json_facade.wait_for_thread_stopped('step', name='step_into')

        # Test step return or 'stepOut'
        json_facade.write_continue()
        json_hit = json_facade.wait_for_thread_stopped(name='step_out')

        json_facade.write_step_out(json_hit.thread_id)
        json_hit = json_facade.wait_for_thread_stopped('step', name='Call')

        json_facade.write_continue()

        writer.finished_ok = True


def test_evaluate(case_setup):
    with case_setup.test_file('_debugger_case_evaluate.py') as writer:
        json_facade = JsonFacade(writer)

        json_facade.write_set_breakpoints(writer.get_line_index_with_content('Break here'))

        json_facade.write_make_initial_run()

        json_hit = json_facade.wait_for_thread_stopped()

        stack_trace_request = json_facade.write_request(
            pydevd_schema.StackTraceRequest(pydevd_schema.StackTraceArguments(threadId=json_hit.thread_id)))
        stack_trace_response = json_facade.wait_for_response(stack_trace_request)
        stack_frame = next(iter(stack_trace_response.body.stackFrames))
        stack_frame_id = stack_frame['id']

        # Test evaluate request that results in 'eval'
        eval_response = json_facade.evaluate('var_1', frameId=stack_frame_id, context='repl')
        assert eval_response.body.result == '5'
        assert eval_response.body.type == 'int'

        # Test evaluate request that results in 'exec'
        exec_response = json_facade.evaluate('var_1 = 6', frameId=stack_frame_id, context='repl')
        assert exec_response.body.result == ''

        # Test evaluate request that results in 'exec' but fails
        exec_response = json_facade.evaluate(
            'var_1 = "abc"/6', frameId=stack_frame_id, context='repl', success=False)
        assert 'TypeError' in exec_response.body.result
        assert 'TypeError' in exec_response.message

        # Evaluate without a frameId.

        # Error because 'foo_value' is not set in 'sys'.
        exec_response = json_facade.evaluate('import email;email.foo_value', success=False)
        assert 'AttributeError' in exec_response.body.result
        assert 'AttributeError' in exec_response.message

        # Reading foo_value didn't work, but 'email' should be in the namespace now.
        json_facade.evaluate('email.foo_value=True')

        # Ok, 'foo_value' is now set in 'email' module.
        exec_response = json_facade.evaluate('email.foo_value')

        # We don't actually get variables without a frameId, we can just evaluate and observe side effects
        # (so, the result is always empty -- or an error).
        assert exec_response.body.result == ''

        json_facade.write_continue()

        writer.finished_ok = True


def test_evaluate_failures(case_setup):
    with case_setup.test_file('_debugger_case_completions.py') as writer:
        json_facade = JsonFacade(writer)

        json_facade.write_set_breakpoints(writer.get_line_index_with_content('Break here'))
        json_facade.write_make_initial_run()

        json_hit = json_facade.wait_for_thread_stopped()

        # First, try with wrong id.
        exec_request = json_facade.write_request(
            pydevd_schema.EvaluateRequest(pydevd_schema.EvaluateArguments('a = 10', frameId=9999, context='repl')))
        exec_response = json_facade.wait_for_response(exec_request)
        assert exec_response.success == False
        assert exec_response.message == 'Wrong ID sent from the client: 9999'

        first_hit = None
        for i in range(2):
            json_hit = json_facade.get_stack_as_json_hit(json_hit.thread_id)
            if i == 0:
                first_hit = json_hit

            if i == 1:
                # Now, check with a previously existing frameId.
                exec_request = json_facade.write_request(
                    pydevd_schema.EvaluateRequest(pydevd_schema.EvaluateArguments('a = 10', frameId=first_hit.frame_id, context='repl')))
                exec_response = json_facade.wait_for_response(exec_request)
                assert exec_response.success == False
                assert exec_response.message == 'Unable to find thread for evaluation.'

            json_facade.write_continue(wait_for_response=i == 0)
            if i == 0:
                json_hit = json_facade.wait_for_thread_stopped()

        writer.finished_ok = True


@pytest.mark.parametrize('max_frames', ['default', 'all', 10])  # -1 = default, 0 = all, 10 = 10 frames
def test_exception_details(case_setup, max_frames):
    with case_setup.test_file('_debugger_case_large_exception_stack.py') as writer:
        json_facade = JsonFacade(writer)

        if max_frames == 'all':
            json_facade.write_launch(maxExceptionStackFrames=0)
            # trace back compresses repeated text
            min_expected_lines = 100
            max_expected_lines = 220
        elif max_frames == 'default':
            json_facade.write_launch()
            # default is all frames
            # trace back compresses repeated text
            min_expected_lines = 100
            max_expected_lines = 220
        else:
            json_facade.write_launch(maxExceptionStackFrames=max_frames)
            min_expected_lines = 10
            max_expected_lines = 21

        json_facade.write_set_exception_breakpoints(['raised'])

        json_facade.write_make_initial_run()
        json_hit = json_facade.wait_for_thread_stopped('exception')

        exc_info_request = json_facade.write_request(
            pydevd_schema.ExceptionInfoRequest(pydevd_schema.ExceptionInfoArguments(json_hit.thread_id)))
        exc_info_response = json_facade.wait_for_response(exc_info_request)

        stack_frames = json_hit.stack_trace_response.body.stackFrames
        assert 100 <= len(stack_frames) <= 104
        assert stack_frames[-1]['name'] == '<module>'
        assert stack_frames[0]['name'] == 'method1'

        body = exc_info_response.body
        assert body.exceptionId.endswith('IndexError')
        assert body.description == 'foo'
        assert normcase(body.details.kwargs['source']) == normcase(writer.TEST_FILE)
        stack_line_count = len(body.details.stackTrace.split('\n'))
        assert  min_expected_lines <= stack_line_count <= max_expected_lines

        json_facade.write_set_exception_breakpoints([])  # Don't stop on reraises.
        json_facade.write_continue()

        writer.finished_ok = True


def test_stack_levels(case_setup):
    with case_setup.test_file('_debugger_case_deep_stacks.py') as writer:
        json_facade = JsonFacade(writer)

        json_facade.write_set_breakpoints(writer.get_line_index_with_content('Break here'))

        json_facade.write_make_initial_run()
        json_hit = json_facade.wait_for_thread_stopped()

        # get full stack
        stack_trace_request = json_facade.write_request(
            pydevd_schema.StackTraceRequest(pydevd_schema.StackTraceArguments(threadId=json_hit.thread_id)))
        stack_trace_response = json_facade.wait_for_response(stack_trace_request)
        full_stack_frames = stack_trace_response.body.stackFrames
        total_frames = stack_trace_response.body.totalFrames

        startFrame = 0
        levels = 20
        received_frames = []
        while startFrame < total_frames:
            stack_trace_request = json_facade.write_request(
                pydevd_schema.StackTraceRequest(pydevd_schema.StackTraceArguments(
                    threadId=json_hit.thread_id,
                    startFrame=startFrame,
                    levels=20)))
            stack_trace_response = json_facade.wait_for_response(stack_trace_request)
            received_frames += stack_trace_response.body.stackFrames
            startFrame += levels

        assert full_stack_frames == received_frames

        json_facade.write_continue()

        writer.finished_ok = True


def test_breakpoint_adjustment(case_setup):
    with case_setup.test_file('_debugger_case_adjust_breakpoint.py') as writer:
        json_facade = JsonFacade(writer)

        json_facade.write_launch()

        bp_requested = writer.get_line_index_with_content('requested')
        bp_expected = writer.get_line_index_with_content('expected')

        set_bp_request = json_facade.write_request(
            pydevd_schema.SetBreakpointsRequest(pydevd_schema.SetBreakpointsArguments(
                source=pydevd_schema.Source(path=writer.TEST_FILE, sourceReference=0),
                breakpoints=[pydevd_schema.SourceBreakpoint(bp_requested).to_dict()]))
        )
        set_bp_response = json_facade.wait_for_response(set_bp_request)
        assert set_bp_response.success
        assert set_bp_response.body.breakpoints[0]['line'] == bp_expected

        json_facade.write_make_initial_run()

        json_hit = json_facade.wait_for_thread_stopped()

        stack_trace_request = json_facade.write_request(
            pydevd_schema.StackTraceRequest(pydevd_schema.StackTraceArguments(threadId=json_hit.thread_id)))
        stack_trace_response = json_facade.wait_for_response(stack_trace_request)
        stack_frame = next(iter(stack_trace_response.body.stackFrames))
        assert stack_frame['line'] == bp_expected

        json_facade.write_continue()

        writer.finished_ok = True


@pytest.mark.skipif(IS_JYTHON, reason='No goto on Jython.')
def test_goto(case_setup):
    with case_setup.test_file('_debugger_case_set_next_statement.py') as writer:
        json_facade = JsonFacade(writer)

        break_line = writer.get_line_index_with_content('Break here')
        step_line = writer.get_line_index_with_content('Step here')
        json_facade.write_set_breakpoints(break_line)

        json_facade.write_make_initial_run()

        json_hit = json_facade.wait_for_thread_stopped()

        stack_trace_request = json_facade.write_request(
            pydevd_schema.StackTraceRequest(pydevd_schema.StackTraceArguments(threadId=json_hit.thread_id)))
        stack_trace_response = json_facade.wait_for_response(stack_trace_request)
        stack_frame = next(iter(stack_trace_response.body.stackFrames))
        assert stack_frame['line'] == break_line

        goto_targets_request = json_facade.write_request(
            pydevd_schema.GotoTargetsRequest(pydevd_schema.GotoTargetsArguments(
                source=pydevd_schema.Source(path=writer.TEST_FILE, sourceReference=0),
                line=step_line)))
        goto_targets_response = json_facade.wait_for_response(goto_targets_request)
        target_id = goto_targets_response.body.targets[0]['id']

        goto_request = json_facade.write_request(
            pydevd_schema.GotoRequest(pydevd_schema.GotoArguments(
                threadId=json_hit.thread_id,
                targetId=12345)))
        goto_response = json_facade.wait_for_response(goto_request)
        assert not goto_response.success

        goto_request = json_facade.write_request(
            pydevd_schema.GotoRequest(pydevd_schema.GotoArguments(
                threadId=json_hit.thread_id,
                targetId=target_id)))
        goto_response = json_facade.wait_for_response(goto_request)

        json_hit = json_facade.wait_for_thread_stopped('goto')

        stack_trace_request = json_facade.write_request(
            pydevd_schema.StackTraceRequest(pydevd_schema.StackTraceArguments(threadId=json_hit.thread_id)))
        stack_trace_response = json_facade.wait_for_response(stack_trace_request)
        stack_frame = next(iter(stack_trace_response.body.stackFrames))
        assert stack_frame['line'] == step_line

        json_facade.write_continue()

        # we hit the breakpoint again. Since we moved back
        json_facade.wait_for_thread_stopped()
        json_facade.write_continue()

        writer.finished_ok = True


def _collect_stack_frames_ending_with(json_hit, end_with_pattern):
    stack_trace_response = json_hit.stack_trace_response
    dont_trace_frames = list(frame for frame in stack_trace_response.body.stackFrames
                             if frame['source']['path'].endswith(end_with_pattern))
    return dont_trace_frames


def _check_dont_trace_filtered_out(json_hit):
    assert _collect_stack_frames_ending_with(json_hit, 'dont_trace.py') == []


def _check_dont_trace_not_filtered_out(json_hit):
    assert len(_collect_stack_frames_ending_with(json_hit, 'dont_trace.py')) == 1


@pytest.mark.parametrize('dbg_property', [
    'dont_trace',
    'trace',
    'change_pattern',
    'dont_trace_after_start'
])
def test_set_debugger_property(case_setup, dbg_property):

    kwargs = {}

    with case_setup.test_file('_debugger_case_dont_trace_test.py', **kwargs) as writer:
        json_facade = JsonFacade(writer)

        json_facade.write_set_breakpoints(writer.get_line_index_with_content('Break here'))

        if dbg_property in ('dont_trace', 'change_pattern', 'dont_trace_after_start'):
            json_facade.write_set_debugger_property([], ['dont_trace.py'])

        if dbg_property == 'change_pattern':
            json_facade.write_set_debugger_property([], ['something_else.py'])

        json_facade.write_make_initial_run()

        json_hit = json_facade.wait_for_thread_stopped()

        if dbg_property in ('dont_trace', 'dont_trace_after_start'):
            _check_dont_trace_filtered_out(json_hit)

        elif dbg_property in ('change_pattern', 'trace'):
            _check_dont_trace_not_filtered_out(json_hit)

        else:
            raise AssertionError('Unexpected: %s' % (dbg_property,))

        if dbg_property == 'dont_trace_after_start':
            json_facade.write_set_debugger_property([], ['something_else.py'])

        json_facade.write_continue()
        json_hit = json_facade.wait_for_thread_stopped()

        if dbg_property in ('dont_trace',):
            _check_dont_trace_filtered_out(json_hit)

        elif dbg_property in ('change_pattern', 'trace', 'dont_trace_after_start'):
            _check_dont_trace_not_filtered_out(json_hit)

        else:
            raise AssertionError('Unexpected: %s' % (dbg_property,))

        json_facade.write_continue()

        writer.finished_ok = True


def test_source_mapping_errors(case_setup):
    from _pydevd_bundle._debug_adapter.pydevd_schema import Source
    from _pydevd_bundle._debug_adapter.pydevd_schema import PydevdSourceMap

    with case_setup.test_file('_debugger_case_source_mapping.py') as writer:
        json_facade = JsonFacade(writer)

        map_to_cell_1_line2 = writer.get_line_index_with_content('map to cell1, line 2')
        map_to_cell_2_line2 = writer.get_line_index_with_content('map to cell2, line 2')

        cell1_map = PydevdSourceMap(map_to_cell_1_line2, map_to_cell_1_line2 + 1, Source(path='<cell1>'), 2)
        cell2_map = PydevdSourceMap(map_to_cell_2_line2, map_to_cell_2_line2 + 1, Source(path='<cell2>'), 2)
        pydevd_source_maps = [
            cell1_map, cell2_map
        ]

        json_facade.write_set_pydevd_source_map(
            Source(path=writer.TEST_FILE),
            pydevd_source_maps=pydevd_source_maps,
        )
        # This will fail because file mappings must be 1:N, not M:N (i.e.: if there's a mapping from file1.py to <cell1>,
        # there can be no other mapping from any other file to <cell1>).
        # This is a limitation to make it easier to remove existing breakpoints when new breakpoints are
        # set to a file (so, any file matching that breakpoint can be removed instead of needing to check
        # which lines are corresponding to that file).
        json_facade.write_set_pydevd_source_map(
            Source(path=os.path.join(os.path.dirname(writer.TEST_FILE), 'foo.py')),
            pydevd_source_maps=pydevd_source_maps,
            success=False,
        )
        json_facade.write_make_initial_run()

        writer.finished_ok = True


def test_source_mapping(case_setup):
    from _pydevd_bundle._debug_adapter.pydevd_schema import Source
    from _pydevd_bundle._debug_adapter.pydevd_schema import PydevdSourceMap

    case_setup.check_non_ascii = True

    with case_setup.test_file('_debugger_case_source_mapping.py') as writer:
        json_facade = JsonFacade(writer)

        json_facade.write_launch(
            debugOptions=['DebugStdLib'],
        )

        map_to_cell_1_line2 = writer.get_line_index_with_content('map to cell1, line 2')
        map_to_cell_2_line2 = writer.get_line_index_with_content('map to cell2, line 2')

        cell1_map = PydevdSourceMap(map_to_cell_1_line2, map_to_cell_1_line2 + 1, Source(path='<cell1>'), 2)
        cell2_map = PydevdSourceMap(map_to_cell_2_line2, map_to_cell_2_line2 + 1, Source(path='<cell2>'), 2)
        pydevd_source_maps = [
            cell1_map, cell2_map, cell2_map,  # The one repeated should be ignored.
        ]

        # Set breakpoints before setting the source map (check that we reapply them).
        json_facade.write_set_breakpoints(map_to_cell_1_line2)

        test_file = writer.TEST_FILE
        if isinstance(test_file, bytes):
            # file is in the filesystem encoding (needed for launch) but protocol needs it in utf-8
            test_file = test_file.decode(file_system_encoding)
            test_file = test_file.encode('utf-8')

        json_facade.write_set_pydevd_source_map(
            Source(path=test_file),
            pydevd_source_maps=pydevd_source_maps,
        )

        json_facade.write_make_initial_run()

        json_facade.wait_for_thread_stopped(line=map_to_cell_1_line2, file=os.path.basename(test_file))
        # Check that we no longer stop at the cell1 breakpoint (its mapping should be removed when
        # the new one is added and we should only stop at cell2).
        json_facade.write_set_breakpoints(map_to_cell_2_line2)
        json_facade.write_continue()

        json_facade.wait_for_thread_stopped(line=map_to_cell_2_line2, file=os.path.basename(test_file))
        json_facade.write_set_breakpoints([])  # Clears breakpoints
        json_facade.write_continue()

        writer.finished_ok = True


@pytest.mark.skipif(not TEST_CHERRYPY, reason='No CherryPy available')
def test_process_autoreload_cherrypy(case_setup_multiprocessing, tmpdir):
    '''
    CherryPy does an os.execv(...) which will kill the running process and replace
    it with a new process when a reload takes place, so, it mostly works as
    a new process connection (everything is the same except that the
    existing process is stopped).
    '''
    port = get_free_port()
    # We write a temp file because we'll change it to autoreload later on.
    f = tmpdir.join('_debugger_case_cherrypy.py')

    tmplt = '''
import cherrypy
cherrypy.config.update({
    'engine.autoreload.on': True,
    'checker.on': False,
    'server.socket_port': %(port)s,
})
class HelloWorld(object):

    @cherrypy.expose
    def index(self):
        print('TEST SUCEEDED')
        return "Hello World %(str)s!"  # break here
    @cherrypy.expose('/exit')
    def exit(self):
        cherrypy.engine.exit()

cherrypy.quickstart(HelloWorld())
'''

    f.write(tmplt % dict(port=port, str='INITIAL'))

    file_to_check = str(f)

    def get_environ(writer):
        env = os.environ.copy()

        env["PYTHONIOENCODING"] = 'utf-8'
        env["PYTHONPATH"] = str(tmpdir)
        return env

    import threading
    from tests_python.debugger_unittest import AbstractWriterThread
    with case_setup_multiprocessing.test_file(file_to_check, get_environ=get_environ) as writer:

        original_ignore_stderr_line = writer._ignore_stderr_line

        @overrides(writer._ignore_stderr_line)
        def _ignore_stderr_line(line):
            if original_ignore_stderr_line(line):
                return True
            return 'ENGINE ' in line or 'CherryPy Checker' in line or 'has an empty config' in line

        writer._ignore_stderr_line = _ignore_stderr_line

        json_facade = JsonFacade(writer)
        json_facade.write_launch(debugOptions=['DebugStdLib'])

        break1_line = writer.get_line_index_with_content('break here')
        json_facade.write_set_breakpoints(break1_line)

        server_socket = writer.server_socket

        class SecondaryProcessWriterThread(AbstractWriterThread):

            TEST_FILE = writer.get_main_filename()
            _sequence = -1

        class SecondaryProcessThreadCommunication(threading.Thread):

            def run(self):
                from tests_python.debugger_unittest import ReaderThread
                expected_connections = 1
                for _ in range(expected_connections):
                    server_socket.listen(1)
                    self.server_socket = server_socket
                    new_sock, addr = server_socket.accept()

                    reader_thread = ReaderThread(new_sock)
                    reader_thread.name = '  *** Multiprocess Reader Thread'
                    reader_thread.start()

                    writer2 = SecondaryProcessWriterThread()

                    writer2.reader_thread = reader_thread
                    writer2.sock = new_sock

                    writer2.write_version()
                    writer2.write_add_breakpoint(break1_line)
                    writer2.write_make_initial_run()

                # Give it some time to startup
                time.sleep(2)
                t = writer.create_request_thread('http://127.0.0.1:%s/' % (port,))
                t.start()

                hit = writer2.wait_for_breakpoint_hit()
                writer2.write_run_thread(hit.thread_id)

                contents = t.wait_for_contents()
                assert 'Hello World NEW!' in contents

                t = writer.create_request_thread('http://127.0.0.1:%s/exit' % (port,))
                t.start()

        secondary_process_thread_communication = SecondaryProcessThreadCommunication()
        secondary_process_thread_communication.start()
        json_facade.write_make_initial_run()

        # Give it some time to startup
        time.sleep(2)

        t = writer.create_request_thread('http://127.0.0.1:%s/' % (port,))
        t.start()
        json_facade.wait_for_thread_stopped()
        json_facade.write_continue()

        contents = t.wait_for_contents()
        assert 'Hello World INITIAL!' in contents

        # Sleep a bit more to make sure that the initial timestamp was gotten in the
        # CherryPy background thread.
        time.sleep(2)
        f.write(tmplt % dict(port=port, str='NEW'))

        secondary_process_thread_communication.join(10)
        if secondary_process_thread_communication.is_alive():
            raise AssertionError('The SecondaryProcessThreadCommunication did not finish')
        writer.finished_ok = True


@pytest.mark.skipif(IS_PY26, reason='Flaky on Python 2.6.')
def test_wait_for_attach(case_setup_remote_attach_to):
    host_port = get_socket_name(close=True)

    def check_thread_events(json_facade):
        json_facade.write_list_threads()
        # Check that we have the started thread event (whenever we reconnect).
        started_events = json_facade.mark_messages(ThreadEvent, lambda x: x.body.reason == 'started')
        assert len(started_events) == 1

    def check_process_event(json_facade, start_method):
        if start_method == 'attach':
            json_facade.write_attach()

        elif start_method == 'launch':
            json_facade.write_launch()

        else:
            raise AssertionError('Unexpected: %s' % (start_method,))

        process_events = json_facade.mark_messages(ProcessEvent)
        assert len(process_events) == 1
        assert next(iter(process_events)).body.startMethod == start_method

    with case_setup_remote_attach_to.test_file('_debugger_case_wait_for_attach.py', host_port[1]) as writer:
        writer.TEST_FILE = debugger_unittest._get_debugger_test_file('_debugger_case_wait_for_attach_impl.py')
        time.sleep(.5)  # Give some time for it to pass the first breakpoint and wait in 'wait_for_attach'.
        writer.start_socket_client(*host_port)

        json_facade = JsonFacade(writer)
        check_thread_events(json_facade)

        break1_line = writer.get_line_index_with_content('Break 1')
        break2_line = writer.get_line_index_with_content('Break 2')
        break3_line = writer.get_line_index_with_content('Break 3')

        pause1_line = writer.get_line_index_with_content('Pause 1')
        pause2_line = writer.get_line_index_with_content('Pause 2')

        check_process_event(json_facade, start_method='launch')
        json_facade.write_set_breakpoints([break1_line, break2_line, break3_line])
        json_facade.write_make_initial_run()
        json_facade.wait_for_thread_stopped(line=break2_line)

        # Upon disconnect, all threads should be running again.
        json_facade.write_disconnect()

        # Connect back (socket should remain open).
        writer.start_socket_client(*host_port)
        json_facade = JsonFacade(writer)
        check_thread_events(json_facade)
        check_process_event(json_facade, start_method='attach')
        json_facade.write_set_breakpoints([break1_line, break2_line, break3_line])
        json_facade.write_make_initial_run()
        json_facade.wait_for_thread_stopped(line=break3_line)

        # Upon disconnect, all threads should be running again.
        json_facade.write_disconnect()

        # Connect back (socket should remain open).
        writer.start_socket_client(*host_port)
        json_facade = JsonFacade(writer)
        check_thread_events(json_facade)
        check_process_event(json_facade, start_method='attach')
        json_facade.write_make_initial_run()

        # Connect back without a disconnect (auto-disconnects previous and connects new client).
        writer.start_socket_client(*host_port)
        json_facade = JsonFacade(writer)
        check_thread_events(json_facade)
        check_process_event(json_facade, start_method='attach')
        json_facade.write_make_initial_run()

        json_facade.write_pause()
        json_hit = json_facade.wait_for_thread_stopped(reason='pause', line=[pause1_line, pause2_line])

        # Change value of 'a' for test to finish.
        json_facade.write_set_variable(json_hit.frame_id, 'a', '10')

        json_facade.write_disconnect()
        writer.finished_ok = True


@pytest.mark.skipif(IS_JYTHON, reason='Flaky on Jython.')
def test_path_translation_and_source_reference(case_setup):

    translated_dir_not_ascii = u'áéíóú汉字'

    if IS_PY2:
        translated_dir_not_ascii = translated_dir_not_ascii.encode(file_system_encoding)

    def get_file_in_client(writer):
        # Instead of using: test_python/_debugger_case_path_translation.py
        # we'll set the breakpoints at foo/_debugger_case_path_translation.py
        file_in_client = os.path.dirname(os.path.dirname(writer.TEST_FILE))
        return os.path.join(os.path.dirname(file_in_client), translated_dir_not_ascii, '_debugger_case_path_translation.py')

    def get_environ(writer):
        env = os.environ.copy()

        env["PYTHONIOENCODING"] = 'utf-8'
        return env

    with case_setup.test_file('_debugger_case_path_translation.py', get_environ=get_environ) as writer:
        file_in_client = get_file_in_client(writer)
        assert 'tests_python' not in file_in_client
        assert translated_dir_not_ascii in file_in_client

        json_facade = JsonFacade(writer)

        bp_line = writer.get_line_index_with_content('break here')
        assert writer.TEST_FILE.endswith('_debugger_case_path_translation.py')
        local_root = os.path.dirname(get_file_in_client(writer))
        if IS_PY2:
            local_root = local_root.decode(file_system_encoding).encode('utf-8')
        json_facade.write_launch(pathMappings=[{
            'localRoot': local_root,
            'remoteRoot': os.path.dirname(writer.TEST_FILE),
        }])
        json_facade.write_set_breakpoints(bp_line, filename=file_in_client)
        json_facade.write_make_initial_run()

        json_hit = json_facade.wait_for_thread_stopped()

        # : :type stack_trace_response: StackTraceResponse
        # : :type stack_trace_response_body: StackTraceResponseBody
        # : :type stack_frame: StackFrame

        # Check stack trace format.
        stack_trace_request = json_facade.write_request(
            pydevd_schema.StackTraceRequest(pydevd_schema.StackTraceArguments(
                threadId=json_hit.thread_id,
                format={'module': True, 'line': True}
        )))
        stack_trace_response = json_facade.wait_for_response(stack_trace_request)
        stack_trace_response_body = stack_trace_response.body
        stack_frame = stack_trace_response_body.stackFrames[0]
        assert stack_frame['name'] == '__main__.call_this : %s' % (bp_line,)

        path = stack_frame['source']['path']
        file_in_client_unicode = file_in_client
        if IS_PY2:
            if isinstance(path, bytes):
                path = path.decode('utf-8')
            if isinstance(file_in_client_unicode, bytes):
                file_in_client_unicode = file_in_client_unicode.decode(file_system_encoding)

        assert path == file_in_client_unicode
        source_reference = stack_frame['source']['sourceReference']
        assert source_reference == 0  # When it's translated the source reference must be == 0

        stack_frame_not_path_translated = stack_trace_response_body.stackFrames[1]
        assert stack_frame_not_path_translated['name'].startswith(
            'tests_python.resource_path_translation.other.call_me_back1 :')

        assert stack_frame_not_path_translated['source']['path'].endswith('other.py')
        source_reference = stack_frame_not_path_translated['source']['sourceReference']
        assert source_reference != 0  # Not translated

        response = json_facade.wait_for_response(json_facade.write_request(
            pydevd_schema.SourceRequest(pydevd_schema.SourceArguments(source_reference))))
        assert "def call_me_back1(callback):" in response.body.content

        json_facade.write_continue()

        writer.finished_ok = True


@pytest.mark.skipif(IS_JYTHON, reason='Flaky on Jython.')
def test_source_reference_no_file(case_setup, tmpdir):

    with case_setup.test_file('_debugger_case_source_reference.py') as writer:
        json_facade = JsonFacade(writer)

        json_facade.write_launch(
            debugOptions=['DebugStdLib'],
            pathMappings=[{
                'localRoot': os.path.dirname(writer.TEST_FILE),
                'remoteRoot': os.path.dirname(writer.TEST_FILE),
        }])

        writer.write_add_breakpoint(writer.get_line_index_with_content('breakpoint'))
        json_facade.write_make_initial_run()

        # First hit is for breakpoint reached via a stack frame that doesn't have source.

        json_hit = json_facade.wait_for_thread_stopped()
        stack_trace_request = json_facade.write_request(
            pydevd_schema.StackTraceRequest(pydevd_schema.StackTraceArguments(
                threadId=json_hit.thread_id,
                format={'module': True, 'line': True}
        )))
        stack_trace_response = json_facade.wait_for_response(stack_trace_request)
        stack_trace_response_body = stack_trace_response.body
        stack_frame = stack_trace_response_body.stackFrames[1]
        assert stack_frame['source']['path'] == '<string>'
        source_reference = stack_frame['source']['sourceReference']
        assert source_reference != 0

        response = json_facade.wait_for_response(json_facade.write_request(
            pydevd_schema.SourceRequest(pydevd_schema.SourceArguments(source_reference))))
        assert not response.success

        json_facade.write_continue()

        # First hit is for breakpoint reached via a stack frame that doesn't have source
        # on disk, but which can be retrieved via linecache.

        json_hit = json_facade.wait_for_thread_stopped()
        stack_trace_request = json_facade.write_request(
            pydevd_schema.StackTraceRequest(pydevd_schema.StackTraceArguments(
                threadId=json_hit.thread_id,
                format={'module': True, 'line': True}
        )))
        stack_trace_response = json_facade.wait_for_response(stack_trace_request)
        stack_trace_response_body = stack_trace_response.body
        stack_frame = stack_trace_response_body.stackFrames[1]
        print(stack_frame['source']['path'])
        assert stack_frame['source']['path'] == '<something>'
        source_reference = stack_frame['source']['sourceReference']
        assert source_reference != 0

        response = json_facade.wait_for_response(json_facade.write_request(
            pydevd_schema.SourceRequest(pydevd_schema.SourceArguments(source_reference))))
        assert response.success
        assert response.body.content == 'foo()\n'

        json_facade.write_continue()
        writer.finished_ok = True


@pytest.mark.skipif(not TEST_DJANGO, reason='No django available')
@pytest.mark.parametrize("jmc", [False, True])
def test_case_django_no_attribute_exception_breakpoint(case_setup_django, jmc):
    import django  # noqa (may not be there if TEST_DJANGO == False)
    django_version = [int(x) for x in django.get_version().split('.')][:2]

    if django_version < [2, 1]:
        pytest.skip('Template exceptions only supporting Django 2.1 onwards.')

    with case_setup_django.test_file(EXPECTED_RETURNCODE='any') as writer:
        json_facade = JsonFacade(writer)

        if jmc:
            writer.write_set_project_roots([debugger_unittest._get_debugger_test_file('my_code')])
            json_facade.write_launch(debugOptions=['Django'])
            json_facade.write_set_exception_breakpoints(['raised'])
        else:
            json_facade.write_launch(debugOptions=['DebugStdLib', 'Django'])
            # Don't set to all 'raised' because we'd stop on standard library exceptions here
            # (which is not something we want).
            json_facade.write_set_exception_breakpoints(exception_options=[
                ExceptionOptions(breakMode='always', path=[
                    {'names': ['Python Exceptions']},
                    {'names': ['AssertionError']},
                ])
            ])

        writer.write_make_initial_run()

        t = writer.create_request_thread('my_app/template_error')
        time.sleep(5)  # Give django some time to get to startup before requesting the page
        t.start()

        json_hit = json_facade.wait_for_thread_stopped('exception', line=7, file='template_error.html')

        stack_trace_request = json_facade.write_request(
            pydevd_schema.StackTraceRequest(pydevd_schema.StackTraceArguments(
                threadId=json_hit.thread_id,
                format={'module': True, 'line': True}
        )))
        stack_trace_response = json_facade.wait_for_response(stack_trace_request)
        stack_trace_response_body = stack_trace_response.body
        stack_frame = next(iter(stack_trace_response_body.stackFrames))
        assert stack_frame['source']['path'].endswith('template_error.html')

        json_hit = json_facade.get_stack_as_json_hit(json_hit.thread_id)
        variables_response = json_facade.get_variables_response(json_hit.frame_id)
        entries = [x for x in variables_response.to_dict()['body']['variables'] if x['name'] == 'entry']
        assert len(entries) == 1
        variables_response = json_facade.get_variables_response(entries[0]['variablesReference'])
        assert variables_response.to_dict()['body']['variables'] == [
            {'name': 'key', 'value': "'v1'", 'type': 'str', 'evaluateName': 'entry.key', 'presentationHint': {'attributes': ['rawString']}, 'variablesReference': 0},
            {'name': 'val', 'value': "'v1'", 'type': 'str', 'evaluateName': 'entry.val', 'presentationHint': {'attributes': ['rawString']}, 'variablesReference': 0}
        ]

        json_facade.write_continue()
        writer.finished_ok = True


@pytest.mark.skipif(not TEST_FLASK, reason='No flask available')
@pytest.mark.parametrize("jmc", [False, True])
def test_case_flask_exceptions(case_setup_flask, jmc):
    with case_setup_flask.test_file(EXPECTED_RETURNCODE='any') as writer:
        json_facade = JsonFacade(writer)

        if jmc:
            writer.write_set_project_roots([debugger_unittest._get_debugger_test_file('my_code')])
            json_facade.write_launch(debugOptions=['Jinja'])
            json_facade.write_set_exception_breakpoints(['raised'])
        else:
            json_facade.write_launch(debugOptions=['DebugStdLib', 'Jinja'])
            # Don't set to all 'raised' because we'd stop on standard library exceptions here
            # (which is not something we want).
            json_facade.write_set_exception_breakpoints(exception_options=[
                ExceptionOptions(breakMode='always', path=[
                    {'names': ['Python Exceptions']},
                    {'names': ['IndexError']},
                ])
            ])
        json_facade.write_make_initial_run()

        t = writer.create_request_thread('/bad_template')
        time.sleep(2)  # Give flask some time to get to startup before requesting the page
        t.start()

        json_facade.wait_for_thread_stopped('exception', line=8, file='bad.html')
        json_facade.write_continue()

        writer.finished_ok = True


@pytest.mark.skipif(IS_APPVEYOR or IS_JYTHON, reason='Flaky on appveyor / Jython encoding issues (needs investigation).')
def test_redirect_output(case_setup):

    def get_environ(writer):
        env = os.environ.copy()

        env["PYTHONIOENCODING"] = 'utf-8'
        return env

    with case_setup.test_file('_debugger_case_redirect.py', get_environ=get_environ) as writer:
        original_ignore_stderr_line = writer._ignore_stderr_line

        json_facade = JsonFacade(writer)

        @overrides(writer._ignore_stderr_line)
        def _ignore_stderr_line(line):
            if original_ignore_stderr_line(line):
                return True
            return line.startswith((
                'text',
                'binary',
                'a'
            ))

        writer._ignore_stderr_line = _ignore_stderr_line

        # Note: writes to stdout and stderr are now synchronous (so, the order
        # must always be consistent and there's a message for each write).
        expected = [
            'text\n',
            'binary or text\n',
            'ação1\n',
        ]

        if sys.version_info[0] >= 3:
            expected.extend((
                'binary\n',
                'ação2\n'.encode(encoding='latin1').decode('utf-8', 'replace'),
                'ação3\n',
            ))

        new_expected = [(x, 'stdout') for x in expected]
        new_expected.extend([(x, 'stderr') for x in expected])

        writer.write_start_redirect()

        writer.write_make_initial_run()
        msgs = []
        ignored = []
        while len(msgs) < len(new_expected):
            try:
                output_event = json_facade.wait_for_json_message(OutputEvent)
                output = output_event.body.output
                category = output_event.body.category
                if IS_PY2:
                    if isinstance(output, unicode):  # noqa -- unicode not available in py3
                        output = output.encode('utf-8')
                    if isinstance(category, unicode):  # noqa -- unicode not available in py3
                        category = category.encode('utf-8')
                msg = (output, category)
            except Exception:
                for msg in msgs:
                    sys.stderr.write('Found: %s\n' % (msg,))
                for msg in new_expected:
                    sys.stderr.write('Expected: %s\n' % (msg,))
                for msg in ignored:
                    sys.stderr.write('Ignored: %s\n' % (msg,))
                raise
            if msg not in new_expected:
                ignored.append(msg)
                continue
            msgs.append(msg)

        if msgs != new_expected:
            print(msgs)
            print(new_expected)
        assert msgs == new_expected
        writer.finished_ok = True


def test_listen_dap_messages(case_setup):

    with case_setup.test_file('_debugger_case_listen_dap_messages.py') as writer:
        json_facade = JsonFacade(writer)
        json_facade.write_launch(debugOptions=['RedirectOutput'],)

        writer.write_add_breakpoint(writer.get_line_index_with_content('Break here'))
        json_facade.write_make_initial_run()

        json_facade.wait_for_thread_stopped()
        json_facade.write_continue()

        writer.finished_ok = True


def _attach_to_writer_pid(writer):
    import pydevd
    import threading
    import subprocess

    assert writer.process is not None

    def attach():
        attach_pydevd_file = os.path.join(os.path.dirname(pydevd.__file__), 'pydevd_attach_to_process', 'attach_pydevd.py')
        subprocess.call([sys.executable, attach_pydevd_file, '--pid', str(writer.process.pid), '--port', str(writer.port), '--protocol', 'http_json'])

    threading.Thread(target=attach).start()

    wait_for_condition(lambda: writer.finished_initialization)


@pytest.mark.parametrize('reattach', [True, False])
@pytest.mark.skipif(not IS_CPYTHON, reason='Attach to pid only available in CPython.')
def test_attach_to_pid(case_setup_remote, reattach):
    import threading

    with case_setup_remote.test_file('_debugger_case_attach_to_pid_simple.py', wait_for_port=False) as writer:
        time.sleep(1)  # Give it some time to initialize to get to the while loop.
        _attach_to_writer_pid(writer)
        json_facade = JsonFacade(writer)

        bp_line = writer.get_line_index_with_content('break here')
        json_facade.write_set_breakpoints(bp_line)
        json_facade.write_make_initial_run()

        json_hit = json_facade.wait_for_thread_stopped(line=bp_line)

        if reattach:
            # This would be the same as a second attach to pid, so, the idea is closing the current
            # connection and then doing a new attach to pid.
            json_facade.write_set_breakpoints([])
            json_facade.write_continue()

            writer.do_kill()  # This will simply close the open sockets without doing anything else.
            time.sleep(1)

            t = threading.Thread(target=writer.start_socket)
            t.start()
            wait_for_condition(lambda: hasattr(writer, 'port'))
            time.sleep(1)
            writer.process = writer.process
            _attach_to_writer_pid(writer)
            wait_for_condition(lambda: hasattr(writer, 'reader_thread'))
            time.sleep(1)

            json_facade = JsonFacade(writer)
            json_facade.write_set_breakpoints(bp_line)
            json_facade.write_make_initial_run()

            json_hit = json_facade.wait_for_thread_stopped(line=bp_line)

        json_facade.write_set_variable(json_hit.frame_id, 'wait', '0')

        json_facade.write_continue()

        writer.finished_ok = True


@pytest.mark.parametrize('apply_multiprocessing_patch', [True, False])
def test_no_subprocess_patching(case_setup_multiprocessing, apply_multiprocessing_patch):
    import threading
    from tests_python.debugger_unittest import AbstractWriterThread

    def update_command_line_args(writer, args):
        ret = debugger_unittest.AbstractWriterThread.update_command_line_args(writer, args)
        ret.insert(ret.index('--qt-support'), '--multiprocess')
        if apply_multiprocessing_patch:
            ret.append('apply-multiprocessing-patch')
        return ret

    with case_setup_multiprocessing.test_file(
            '_debugger_case_no_subprocess_patching.py',
            update_command_line_args=update_command_line_args
        ) as writer:
        json_facade = JsonFacade(writer)
        json_facade.write_launch()

        break1_line = writer.get_line_index_with_content('break 1 here')
        break2_line = writer.get_line_index_with_content('break 2 here')
        json_facade.write_set_breakpoints([break1_line, break2_line])

        server_socket = writer.server_socket

        class SecondaryProcessWriterThread(AbstractWriterThread):

            TEST_FILE = writer.get_main_filename()
            _sequence = -1

        class SecondaryProcessThreadCommunication(threading.Thread):

            def run(self):
                from tests_python.debugger_unittest import ReaderThread
                expected_connections = 1
                if sys.platform != 'win32' and IS_PY2:
                    # Note: on linux on Python 2 CPython subprocess.call will actually
                    # create a fork first (at which point it'll connect) and then, later on it'll
                    # call the main (as if it was a clean process as if PyDB wasn't created
                    # the first time -- the debugger will still work, but it'll do an additional
                    # connection).
                    expected_connections = 2

                for _ in range(expected_connections):
                    server_socket.listen(1)
                    self.server_socket = server_socket
                    new_sock, addr = server_socket.accept()

                    reader_thread = ReaderThread(new_sock)
                    reader_thread.name = '  *** Multiprocess Reader Thread'
                    reader_thread.start()

                    writer2 = SecondaryProcessWriterThread()
                    writer2.reader_thread = reader_thread
                    writer2.sock = new_sock
                    json_facade2 = JsonFacade(writer2)

                    json_facade2.write_set_breakpoints([break1_line, break2_line])
                    json_facade2.write_make_initial_run()

                json_facade2.wait_for_thread_stopped()
                json_facade2.write_continue()

        if apply_multiprocessing_patch:
            secondary_process_thread_communication = SecondaryProcessThreadCommunication()
            secondary_process_thread_communication.start()
            time.sleep(.1)

        json_facade.write_make_initial_run()
        json_facade.wait_for_thread_stopped()
        json_facade.write_continue()

        if apply_multiprocessing_patch:
            secondary_process_thread_communication.join(10)
            if secondary_process_thread_communication.is_alive():
                raise AssertionError('The SecondaryProcessThreadCommunication did not finish')
        writer.finished_ok = True


def test_pydevd_systeminfo(case_setup):
    with case_setup.test_file('_debugger_case_print.py') as writer:
        json_facade = JsonFacade(writer)

        writer.write_add_breakpoint(writer.get_line_index_with_content('Break here'))

        json_facade.write_make_initial_run()

        json_hit = json_facade.wait_for_thread_stopped()
        assert json_hit.thread_id

        info_request = json_facade.write_request(
            pydevd_schema.PydevdSystemInfoRequest(
                pydevd_schema.PydevdSystemInfoArguments()
            )
        )
        info_response = json_facade.wait_for_response(info_request)
        body = info_response.to_dict()['body']

        assert body['python']['version'] == PY_VERSION_STR
        assert body['python']['implementation']['name'] == PY_IMPL_NAME
        assert body['python']['implementation']['version'] == PY_IMPL_VERSION_STR
        assert 'description' in body['python']['implementation']

        assert body['platform'] == {'name': sys.platform}

        assert 'pid' in body['process']
        assert 'ppid' in body['process']
        assert body['process']['executable'] == sys.executable
        assert body['process']['bitness'] == 64 if IS_64BIT_PROCESS else 32

        json_facade.write_continue()

        writer.finished_ok = True


@pytest.mark.parametrize('scenario', [
    'terminate_request',
    'terminate_debugee'
])
@pytest.mark.parametrize('check_subprocesses', [
    'no_subprocesses',
    'kill_subprocesses',
    'kill_subprocesses_ignore_pid',
    'dont_kill_subprocesses',
])
def test_terminate(case_setup, scenario, check_subprocesses):
    import psutil

    def check_test_suceeded_msg(writer, stdout, stderr):
        return 'TEST SUCEEDED' not in ''.join(stdout)

    def update_command_line_args(writer, args):
        ret = debugger_unittest.AbstractWriterThread.update_command_line_args(writer, args)
        if check_subprocesses in ('kill_subprocesses', 'dont_kill_subprocesses'):
            ret.append('check-subprocesses')
        if check_subprocesses in ('kill_subprocesses_ignore_pid',):
            ret.append('check-subprocesses-ignore-pid')
        return ret

    with case_setup.test_file(
        '_debugger_case_terminate.py',
        check_test_suceeded_msg=check_test_suceeded_msg,
        update_command_line_args=update_command_line_args,
        EXPECTED_RETURNCODE='any' if check_subprocesses == 'kill_subprocesses_ignore_pid' else 0,
        ) as writer:
        json_facade = JsonFacade(writer)
        if check_subprocesses == 'dont_kill_subprocesses':
            json_facade.write_launch(terminateChildProcesses=False)

        json_facade.write_make_initial_run()
        response = json_facade.write_initialize()
        pid = response.to_dict()['body']['pydevd']['processId']

        if check_subprocesses in ('kill_subprocesses', 'dont_kill_subprocesses', 'kill_subprocesses_ignore_pid'):
            process_ids_to_check = [pid]
            p = psutil.Process(pid)

            def wait_for_child_processes():
                children = p.children(recursive=True)
                found = len(children)
                if found == 8:
                    process_ids_to_check.extend([x.pid for x in children])
                    return True
                return False

            wait_for_condition(wait_for_child_processes)

        if scenario == 'terminate_request':
            json_facade.write_terminate()
        elif scenario == 'terminate_debugee':
            json_facade.write_disconnect(terminate_debugee=True)
        else:
            raise AssertionError('Unexpected: %s' % (scenario,))
        json_facade.wait_for_terminated()

        if check_subprocesses in ('kill_subprocesses', 'dont_kill_subprocesses', 'kill_subprocesses_ignore_pid'):

            def is_pid_alive(pid):
                # Note: the process may be a zombie process in Linux
                # (althought it's killed it remains in that state
                # because we're monitoring it).
                try:
                    proc = psutil.Process(pid)
                    if proc.status() == psutil.STATUS_ZOMBIE:
                        return False
                except psutil.NoSuchProcess:
                    return False
                return True

            def get_live_pids():
                return [pid for pid in process_ids_to_check if is_pid_alive(pid)]

            if check_subprocesses == 'kill_subprocesses':

                def all_pids_exited():
                    live_pids = get_live_pids()
                    if live_pids:
                        return False

                    return True

                wait_for_condition(all_pids_exited)

            elif check_subprocesses == 'kill_subprocesses_ignore_pid':

                def all_pids_exited():
                    live_pids = get_live_pids()
                    if len(live_pids) == 1:
                        return False

                    return True

                wait_for_condition(all_pids_exited)

                # Now, let's kill the remaining process ourselves.
                for pid in get_live_pids():
                    proc = psutil.Process(pid)
                    proc.kill()

            else:  # 'dont_kill_subprocesses'
                time.sleep(1)

                def only_main_pid_exited():
                    live_pids = get_live_pids()
                    if len(live_pids) == len(process_ids_to_check) - 1:
                        return True

                    return False

                wait_for_condition(only_main_pid_exited)

                # Now, let's kill the remaining processes ourselves.
                for pid in get_live_pids():
                    proc = psutil.Process(pid)
                    proc.kill()

        writer.finished_ok = True


def test_access_token(case_setup):

    def update_command_line_args(self, args):
        args.insert(1, '--json-dap-http')
        args.insert(2, '--access-token')
        args.insert(3, 'bar123')
        args.insert(4, '--ide-access-token')
        args.insert(5, 'foo321')
        return args

    with case_setup.test_file('_debugger_case_pause_continue.py', update_command_line_args=update_command_line_args) as writer:
        json_facade = JsonFacade(writer, send_json_startup_messages=False)

        response = json_facade.write_set_debugger_property(multi_threads_single_notification=True, success=False)
        assert response.message == "Client not authenticated."

        response = json_facade.write_authorize(access_token='wrong', success=False)
        assert response.message == "Client not authenticated."

        response = json_facade.write_set_debugger_property(multi_threads_single_notification=True, success=False)
        assert response.message == "Client not authenticated."

        authorize_response = json_facade.write_authorize(access_token='bar123', success=True)
        # : :type authorize_response:PydevdAuthorizeResponse
        assert authorize_response.body.clientAccessToken == 'foo321'

        json_facade.write_set_debugger_property(multi_threads_single_notification=True)
        json_facade.write_launch()

        break_line = writer.get_line_index_with_content('Pause here and change loop to False')
        json_facade.write_set_breakpoints(break_line)
        json_facade.write_make_initial_run()

        json_facade.wait_for_json_message(ThreadEvent, lambda event: event.body.reason == 'started')
        json_facade.wait_for_thread_stopped(line=break_line)

        # : :type response: ThreadsResponse
        response = json_facade.write_list_threads()
        assert len(response.body.threads) == 1
        assert next(iter(response.body.threads))['name'] == 'MainThread'

        json_facade.write_disconnect()

        response = json_facade.write_authorize(access_token='wrong', success=False)
        assert response.message == "Client not authenticated."

        authorize_response = json_facade.write_authorize(access_token='bar123')
        assert authorize_response.body.clientAccessToken == 'foo321'

        json_facade.write_set_breakpoints(break_line)
        json_hit = json_facade.wait_for_thread_stopped(line=break_line)
        json_facade.write_set_variable(json_hit.frame_id, 'loop', 'False')
        json_facade.write_continue()
        json_facade.wait_for_terminated()

        writer.finished_ok = True


if __name__ == '__main__':
    pytest.main(['-k', 'test_case_skipping_filters', '-s'])

