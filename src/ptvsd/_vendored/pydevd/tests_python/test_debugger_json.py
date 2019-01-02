from _pydevd_bundle._debug_adapter.pydevd_base_schema import from_json
from _pydevd_bundle._debug_adapter.pydevd_schema import ThreadEvent, ThreadsResponse
from tests_python.debugger_unittest import IS_JYTHON
import pytest

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

    def write_request(self, request):
        seq = self.writer.next_seq()
        request.seq = seq
        self.writer.write_with_content_len(request.to_json())


@pytest.mark.skipif(IS_JYTHON, reason='Must check why it is failing in Jython.')
def test_case_json_protocol(case_setup):
    with case_setup.test_file('_debugger_case_print.py') as writer:
        json_facade = JsonFacade(writer)

        writer.write_set_protocol('http_json')
        writer.write_add_breakpoint(writer.get_line_index_with_content('Break here'))
        writer.write_make_initial_run()

        json_facade.wait_for_json_message(ThreadEvent, lambda event: event.body.reason == 'started')

        hit = writer.wait_for_breakpoint_hit()
        thread_id = hit.thread_id
        frame_id = hit.frame_id

        writer.write_list_threads()
        response = json_facade.wait_for_json_message(ThreadsResponse)
        assert len(response.body.threads) == 1
        assert next(iter(response.body.threads))['name'] == 'MainThread'

        writer.write_run_thread(thread_id)

        writer.finished_ok = True


def test_case_completions_json(case_setup):
    from _pydevd_bundle._debug_adapter import pydevd_schema
    with case_setup.test_file('_debugger_case_print.py') as writer:
        json_facade = JsonFacade(writer)

        writer.write_set_protocol('http_json')
        writer.write_add_breakpoint(writer.get_line_index_with_content('Break here'))
        writer.write_make_initial_run()

        hit = writer.wait_for_breakpoint_hit()
        thread_id = hit.thread_id
        frame_id = hit.frame_id

        completions_arguments = pydevd_schema.CompletionsArguments(
            'dict.', 6, frameId=(thread_id, frame_id), line=0)
        completions_request = pydevd_schema.CompletionsRequest(completions_arguments)
        json_facade.write_request(completions_request)

        response = json_facade.wait_for_json_message(pydevd_schema.CompletionsResponse)
        labels = [x['label'] for x in response.body.targets]
        assert set(labels).issuperset(set(['__contains__', 'items', 'keys', 'values']))

        completions_arguments = pydevd_schema.CompletionsArguments(
            'dict.item', 10, frameId=(thread_id, frame_id))
        completions_request = pydevd_schema.CompletionsRequest(completions_arguments)
        json_facade.write_request(completions_request)

        response = json_facade.wait_for_json_message(pydevd_schema.CompletionsResponse)
        if IS_JYTHON:
            assert response.body.targets == [
                {'start': 5, 'length': 4, 'type': 'keyword', 'label': 'items'}]
        else:
            assert response.body.targets == [
                {'start': 5, 'length': 4, 'type': 'function', 'label': 'items'}]

        writer.write_run_thread(thread_id)

        writer.finished_ok = True
