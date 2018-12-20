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

