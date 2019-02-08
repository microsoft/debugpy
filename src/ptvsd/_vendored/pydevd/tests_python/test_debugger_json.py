import pytest

from _pydevd_bundle._debug_adapter import pydevd_schema, pydevd_base_schema
from _pydevd_bundle._debug_adapter.pydevd_base_schema import from_json
from _pydevd_bundle._debug_adapter.pydevd_schema import ThreadEvent
from tests_python import debugger_unittest
from tests_python.debugger_unittest import IS_JYTHON, REASON_STEP_INTO, REASON_STEP_OVER
import json

pytest_plugins = [
    str('tests_python.debugger_fixtures'),
]


class JsonFacade(object):

    def __init__(self, writer):
        self.writer = writer

    def wait_for_json_message(self, expected_class, accept_message=lambda obj:True):

        def accept_json_message(msg):
            if msg.startswith('{'):
                decoded_msg = from_json(msg)
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

        return self.wait_for_json_message(response_class, accept_message)

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
        configuration_done_request = self.write_request(pydevd_schema.ConfigurationDoneRequest())
        return self.wait_for_response(configuration_done_request)

    def write_list_threads(self):
        return self.wait_for_response(self.write_request(pydevd_schema.ThreadsRequest()))

    def write_set_breakpoints(self, lines, filename=None, line_to_info=None):
        '''
        Adds a breakpoint.
        '''
        if isinstance(lines, int):
            lines = [lines]

        if line_to_info is None:
            line_to_info = {}

        if filename is None:
            filename = self.writer.get_main_filename()

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

        # : :type body: SetBreakpointsResponseBody
        assert len(body.breakpoints) == len(lines)
        lines_in_response = [b['line'] for b in body.breakpoints]
        assert set(lines_in_response) == set(lines)

    def write_launch(self, **arguments):
        arguments['noDebug'] = False
        request = {'type': 'request', 'command': 'launch', 'arguments': arguments, 'seq':-1}
        self.wait_for_response(self.write_request(request))

    def write_disconnect(self):
        arguments = pydevd_schema.DisconnectArguments(terminateDebuggee=False)
        request = pydevd_schema.DisconnectRequest(arguments)
        self.wait_for_response(self.write_request(request))


def test_case_json_logpoints(case_setup):
    with case_setup.test_file('_debugger_case_change_breaks.py') as writer:
        json_facade = JsonFacade(writer)

        writer.write_set_protocol('http_json')
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
            msg, ctx = writer.wait_for_output()
            if ctx == 'stdout':
                msg = msg.strip()
                if msg == "var '_a' is 2":
                    messages.append(msg)

                if len(messages) == 2:
                    break

        # Just one hit at the end (break 3).
        hit = writer.wait_for_breakpoint_hit()
        writer.write_run_thread(hit.thread_id)

        writer.finished_ok = True


@pytest.mark.skipif(IS_JYTHON, reason='Must check why it is failing in Jython.')
def test_case_json_change_breaks(case_setup):
    with case_setup.test_file('_debugger_case_change_breaks.py') as writer:
        json_facade = JsonFacade(writer)

        writer.write_set_protocol('http_json')
        json_facade.write_launch()
        json_facade.write_set_breakpoints(writer.get_line_index_with_content('break 1'))
        json_facade.write_make_initial_run()
        hit = writer.wait_for_breakpoint_hit()
        writer.write_run_thread(hit.thread_id)

        hit = writer.wait_for_breakpoint_hit()
        writer.write_run_thread(hit.thread_id)

        json_facade.write_set_breakpoints([])
        writer.write_run_thread(hit.thread_id)

        writer.finished_ok = True


@pytest.mark.skipif(IS_JYTHON, reason='Must check why it is failing in Jython.')
def test_case_json_protocol(case_setup):
    with case_setup.test_file('_debugger_case_print.py') as writer:
        json_facade = JsonFacade(writer)

        writer.write_set_protocol('http_json')
        json_facade.write_launch()
        json_facade.write_set_breakpoints(writer.get_line_index_with_content('Break here'))
        json_facade.write_make_initial_run()

        json_facade.wait_for_json_message(ThreadEvent, lambda event: event.body.reason == 'started')

        hit = writer.wait_for_breakpoint_hit()
        thread_id = hit.thread_id
        frame_id = hit.frame_id

        # : :type response: ThreadsResponse
        response = json_facade.write_list_threads()
        assert len(response.body.threads) == 1
        assert next(iter(response.body.threads))['name'] == 'MainThread'

        # Removes breakpoints and proceeds running.
        json_facade.write_disconnect()

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

        writer.write_set_protocol('http_json')
        if custom_setup == 'set_exclude_launch_path_match_filename':
            json_facade.write_launch(
                debugStdLib=True,
                rules=[
                    {'path': '**/other.py', 'include':False},
                ]
            )

        elif custom_setup == 'set_exclude_launch_path_match_folder':
            json_facade.write_launch(
                debugStdLib=True,
                rules=[
                    {'path': debugger_unittest._get_debugger_test_file('not_my_code'), 'include':False},
                ]
            )

        elif custom_setup == 'set_exclude_launch_module_full':
            json_facade.write_launch(
                debugStdLib=True,
                rules=[
                    {'module': 'not_my_code.other', 'include':False},
                ]
            )

        elif custom_setup == 'set_exclude_launch_module_prefix':
            json_facade.write_launch(
                debugStdLib=True,
                rules=[
                    {'module': 'not_my_code', 'include':False},
                ]
            )

        elif custom_setup == 'set_just_my_code':
            writer.write_set_project_roots([debugger_unittest._get_debugger_test_file('my_code')])
            json_facade.write_launch(debugStdLib=False)

        elif custom_setup == 'set_just_my_code_and_include':
            # I.e.: nothing in my_code (add it with rule).
            writer.write_set_project_roots([debugger_unittest._get_debugger_test_file('launch')])
            json_facade.write_launch(
                debugStdLib=False,
                rules=[
                    {'module': '__main__', 'include':True},
                ]
            )

        else:
            raise AssertionError('Unhandled: %s' % (custom_setup,))

        json_facade.write_set_breakpoints(writer.get_line_index_with_content('break here'))
        json_facade.write_make_initial_run()

        json_facade.wait_for_json_message(ThreadEvent, lambda event: event.body.reason == 'started')

        hit = writer.wait_for_breakpoint_hit()

        writer.write_step_in(hit.thread_id)
        hit = writer.wait_for_breakpoint_hit(reason=REASON_STEP_INTO)
        assert hit.name == 'callback1'

        writer.write_step_in(hit.thread_id)
        hit = writer.wait_for_breakpoint_hit(reason=REASON_STEP_INTO)
        assert hit.name == 'callback2'

        writer.write_step_over(hit.thread_id)
        hit = writer.wait_for_breakpoint_hit(reason=REASON_STEP_INTO)  # Note: goes from step over to step into
        assert hit.name == 'callback1'

        writer.write_step_over(hit.thread_id)
        hit = writer.wait_for_breakpoint_hit(reason=REASON_STEP_INTO)  # Note: goes from step over to step into
        assert hit.name == '<module>'

        writer.write_step_over(hit.thread_id)
        hit = writer.wait_for_breakpoint_hit(reason=REASON_STEP_OVER)
        assert hit.name == '<module>'

        writer.write_step_over(hit.thread_id)

        if IS_JYTHON:
            writer.write_run_thread(hit.thread_id)
        else:
            writer.write_step_over(hit.thread_id)

        writer.finished_ok = True


def test_case_completions_json(case_setup):
    with case_setup.test_file('_debugger_case_print.py') as writer:
        json_facade = JsonFacade(writer)

        writer.write_set_protocol('http_json')
        writer.write_add_breakpoint(writer.get_line_index_with_content('Break here'))

        json_facade.write_make_initial_run()

        hit = writer.wait_for_breakpoint_hit()
        thread_id = hit.thread_id
        frame_id = hit.frame_id

        completions_arguments = pydevd_schema.CompletionsArguments(
            'dict.', 6, frameId=(thread_id, frame_id), line=0)
        completions_request = json_facade.write_request(
            pydevd_schema.CompletionsRequest(completions_arguments))

        response = json_facade.wait_for_response(completions_request)
        labels = [x['label'] for x in response.body.targets]
        assert set(labels).issuperset(set(['__contains__', 'items', 'keys', 'values']))

        completions_arguments = pydevd_schema.CompletionsArguments(
            'dict.item', 10, frameId=(thread_id, frame_id))
        completions_request = json_facade.write_request(
            pydevd_schema.CompletionsRequest(completions_arguments))

        response = json_facade.wait_for_response(completions_request)
        if IS_JYTHON:
            assert response.body.targets == [
                {'start': 5, 'length': 4, 'type': 'keyword', 'label': 'items'}]
        else:
            assert response.body.targets == [
                {'start': 5, 'length': 4, 'type': 'function', 'label': 'items'}]

        writer.write_run_thread(thread_id)

        writer.finished_ok = True


if __name__ == '__main__':
    pytest.main(['-k', 'test_case_skipping_filters', '-s'])

