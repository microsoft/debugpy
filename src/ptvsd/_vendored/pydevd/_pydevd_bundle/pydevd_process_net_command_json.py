from _pydevd_bundle._debug_adapter import pydevd_base_schema
import json
from _pydevd_bundle.pydevd_comm import InternalGetCompletions


class _PyDevJsonCommandProcessor(object):

    def __init__(self, from_json):
        self.from_json = from_json

    def process_net_command_json(self, py_db, json_contents):
        '''
        Processes a debug adapter protocol json command.
        '''

        DEBUG = False

        request = self.from_json(json_contents)

        if DEBUG:
            print('Process %s: %s\n' % (
                request.__class__.__name__, json.dumps(request.to_dict(), indent=4, sort_keys=True),))

        assert request.type == 'request'
        method_name = 'on_%s_request' % (request.command.lower(),)
        on_request = getattr(self, method_name, None)
        if on_request is not None:
            if DEBUG:
                print('Handled in pydevd: %s (in _PyDevdCommandProcessor).\n' % (method_name,))

            py_db._main_lock.acquire()
            try:

                cmd = on_request(py_db, request)
                if cmd is not None:
                    py_db.writer.add_command(cmd)
            finally:
                py_db._main_lock.release()

        else:
            print('Unhandled: %s not available in _PyDevdCommandProcessor.\n' % (method_name,))
            
    def on_completions_request(self, py_db, request):
        '''
        :param CompletionsRequest request:
        '''
        arguments = request.arguments  # : :type arguments: CompletionsArguments
        seq = request.seq
        text = arguments.text
        thread_id, frame_id = arguments.frameId

        # Note: line and column are 1-based (convert to 0-based for pydevd).
        column = arguments.column - 1

        if arguments.line is None:
            # line is optional
            line = -1
        else:
            line = arguments.line - 1

        int_cmd = InternalGetCompletions(seq, thread_id, frame_id, text, line=line, column=column)
        py_db.post_internal_command(int_cmd, thread_id)


process_net_command_json = _PyDevJsonCommandProcessor(pydevd_base_schema.from_json).process_net_command_json
