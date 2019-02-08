from functools import partial
import itertools
import json
import os

from _pydevd_bundle._debug_adapter import pydevd_base_schema
from _pydevd_bundle._debug_adapter.pydevd_schema import SourceBreakpoint
from _pydevd_bundle.pydevd_api import PyDevdAPI
from _pydevd_bundle.pydevd_comm_constants import CMD_RETURN
from _pydevd_bundle.pydevd_filtering import ExcludeFilter
from _pydevd_bundle.pydevd_json_debug_options import _extract_debug_options
from _pydevd_bundle.pydevd_net_command import NetCommand
from _pydevd_bundle.pydevd_utils import convert_dap_log_message_to_expression


def _convert_rules_to_exclude_filters(rules, filename_to_server, on_error):
    exclude_filters = []
    if not isinstance(rules, list):
        on_error('Invalid "rules" (expected list of dicts). Found: %s' % (rules,))

    else:
        directory_exclude_filters = []
        module_exclude_filters = []
        glob_exclude_filters = []

        for rule in rules:
            if not isinstance(rule, dict):
                on_error('Invalid "rules" (expected list of dicts). Found: %s' % (rules,))
                continue

            include = rule.get('include')
            if include is None:
                on_error('Invalid "rule" (expected dict with "include"). Found: %s' % (rule,))
                continue

            path = rule.get('path')
            module = rule.get('module')
            if path is None and module is None:
                on_error('Invalid "rule" (expected dict with "path" or "module"). Found: %s' % (rule,))
                continue

            if path is not None:
                glob_pattern = path
                if '*' not in path and '?' not in path:
                    path = filename_to_server(path)

                    if os.path.isdir(glob_pattern):
                        # If a directory was specified, add a '/**'
                        # to be consistent with the glob pattern required
                        # by pydevd.
                        if not glob_pattern.endswith('/') and not glob_pattern.endswith('\\'):
                            glob_pattern += '/'
                        glob_pattern += '**'
                    directory_exclude_filters.append(ExcludeFilter(glob_pattern, not include, True))
                else:
                    glob_exclude_filters.append(ExcludeFilter(glob_pattern, not include, True))

            elif module is not None:
                module_exclude_filters.append(ExcludeFilter(module, not include, False))

            else:
                on_error('Internal error: expected path or module to be specified.')

        # Note that we have to sort the directory/module exclude filters so that the biggest
        # paths match first.
        # i.e.: if we have:
        # /sub1/sub2/sub3
        # a rule with /sub1/sub2 would match before a rule only with /sub1.
        directory_exclude_filters = sorted(directory_exclude_filters, key=lambda exclude_filter:-len(exclude_filter.name))
        module_exclude_filters = sorted(module_exclude_filters, key=lambda exclude_filter:-len(exclude_filter.name))
        exclude_filters = directory_exclude_filters + glob_exclude_filters + module_exclude_filters

    return exclude_filters


class _PyDevJsonCommandProcessor(object):

    def __init__(self, from_json):
        self.from_json = from_json
        self.api = PyDevdAPI()
        self._debug_options = {}
        self._next_breakpoint_id = partial(next, itertools.count(0))

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
        if on_request is None:
            print('Unhandled: %s not available in _PyDevJsonCommandProcessor.\n' % (method_name,))
            return

        if DEBUG:
            print('Handled in pydevd: %s (in _PyDevJsonCommandProcessor).\n' % (method_name,))

        py_db._main_lock.acquire()
        try:

            cmd = on_request(py_db, request)
            if cmd is not None:
                py_db.writer.add_command(cmd)
        finally:
            py_db._main_lock.release()

    def on_configurationdone_request(self, py_db, request):
        '''
        :param ConfigurationDoneRequest request:
        '''
        self.api.run(py_db)
        configuration_done_response = pydevd_base_schema.build_response(request)
        return NetCommand(CMD_RETURN, 0, configuration_done_response.to_dict(), is_json=True)

    def on_threads_request(self, py_db, request):
        '''
        :param ThreadsRequest request:
        '''
        return self.api.list_threads(py_db, request.seq)

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

        self.api.request_completions(py_db, seq, thread_id, frame_id, text, line=line, column=column)

    def _set_debug_options(self, py_db, args):
        rules = args.get('rules')
        exclude_filters = []

        if rules is not None:
            exclude_filters = _convert_rules_to_exclude_filters(
                rules, self.api.filename_to_server, lambda msg:self.api.send_error_message(py_db, msg))

        self.api.set_exclude_filters(py_db, exclude_filters)

        self._debug_options = _extract_debug_options(
            args.get('options'),
            args.get('debugOptions'),
        )
        debug_stdlib = self._debug_options.get('DEBUG_STDLIB', False)
        self.api.set_use_libraries_filter(py_db, not debug_stdlib)

    def on_launch_request(self, py_db, request):
        '''
        :param LaunchRequest request:
        '''
        self._set_debug_options(py_db, request.arguments.kwargs)
        response = pydevd_base_schema.build_response(request)
        return NetCommand(CMD_RETURN, 0, response.to_dict(), is_json=True)

    def on_attach_request(self, py_db, request):
        '''
        :param AttachRequest request:
        '''
        self._set_debug_options(py_db, request.arguments.kwargs)
        response = pydevd_base_schema.build_response(request)
        return NetCommand(CMD_RETURN, 0, response.to_dict(), is_json=True)

    def _get_hit_condition_expression(self, hit_condition):
        '''Following hit condition values are supported

        * x or == x when breakpoint is hit x times
        * >= x when breakpoint is hit more than or equal to x times
        * % x when breakpoint is hit multiple of x times

        Returns '@HIT@ == x' where @HIT@ will be replaced by number of hits
        '''
        if not hit_condition:
            return None

        expr = hit_condition.strip()
        try:
            int(expr)
            return '@HIT@ == {}'.format(expr)
        except ValueError:
            pass

        if expr.startswith('%'):
            return '@HIT@ {} == 0'.format(expr)

        if expr.startswith('==') or \
            expr.startswith('>') or \
            expr.startswith('<'):
            return '@HIT@ {}'.format(expr)

        return hit_condition

    def on_disconnect_request(self, py_db, request):
        '''
        :param DisconnectRequest request:
        '''
        self.api.remove_all_breakpoints(py_db, filename='*')
        self.api.request_resume_thread(thread_id='*')

        response = pydevd_base_schema.build_response(request)
        return NetCommand(CMD_RETURN, 0, response.to_dict(), is_json=True)

    def on_setbreakpoints_request(self, py_db, request):
        '''
        :param SetBreakpointsRequest request:
        '''
        arguments = request.arguments  # : :type arguments: SetBreakpointsArguments
        filename = arguments.source.path
        filename = self.api.filename_to_server(filename)
        func_name = 'None'

        self.api.remove_all_breakpoints(py_db, filename)

        btype = 'python-line'
        suspend_policy = 'ALL'

        if not filename.lower().endswith('.py'):
            if self._debug_options.get('DJANGO_DEBUG', False):
                btype = 'django-line'
            elif self._debug_options.get('FLASK_DEBUG', False):
                btype = 'jinja2-line'

        breakpoints_set = []

        for source_breakpoint in arguments.breakpoints:
            source_breakpoint = SourceBreakpoint(**source_breakpoint)
            line = source_breakpoint.line
            condition = source_breakpoint.condition
            breakpoint_id = line

            hit_condition = self._get_hit_condition_expression(source_breakpoint.hitCondition)
            log_message = source_breakpoint.logMessage
            if not log_message:
                is_logpoint = None
                expression = None
            else:
                is_logpoint = True
                expression = convert_dap_log_message_to_expression(log_message)

            self.api.add_breakpoint(
                py_db, filename, btype, breakpoint_id, line, condition, func_name, expression, suspend_policy, hit_condition, is_logpoint)

            # Note that the id is made up (the id for pydevd is unique only within a file, so, the
            # line is used for it).
            # Also, the id is currently not used afterwards, so, we don't even keep a mapping.
            breakpoints_set.append({'id':self._next_breakpoint_id(), 'verified': True, 'line': line})

        body = {'breakpoints': breakpoints_set}
        set_breakpoints_response = pydevd_base_schema.build_response(request, kwargs={'body':body})
        return NetCommand(CMD_RETURN, 0, set_breakpoints_response.to_dict(), is_json=True)


process_net_command_json = _PyDevJsonCommandProcessor(pydevd_base_schema.from_json).process_net_command_json
