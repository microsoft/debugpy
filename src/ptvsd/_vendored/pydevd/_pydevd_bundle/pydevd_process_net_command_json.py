from functools import partial
import itertools
import json
import linecache
import os

from _pydevd_bundle._debug_adapter import pydevd_base_schema
from _pydevd_bundle._debug_adapter.pydevd_schema import (SourceBreakpoint, ScopesResponseBody, Scope,
    VariablesResponseBody, SetVariableResponseBody, ModulesResponseBody, SourceResponseBody)
from _pydevd_bundle.pydevd_api import PyDevdAPI
from _pydevd_bundle.pydevd_comm_constants import (
    CMD_RETURN, CMD_STEP_OVER_MY_CODE, CMD_STEP_OVER, CMD_STEP_INTO_MY_CODE,
    CMD_STEP_INTO, CMD_STEP_RETURN_MY_CODE, CMD_STEP_RETURN)
from _pydevd_bundle.pydevd_filtering import ExcludeFilter
from _pydevd_bundle.pydevd_json_debug_options import _extract_debug_options
from _pydevd_bundle.pydevd_net_command import NetCommand
from _pydevd_bundle.pydevd_utils import convert_dap_log_message_to_expression
import pydevd_file_utils


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

        request = self.from_json(json_contents, update_ids_from_dap=True)

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
        return NetCommand(CMD_RETURN, 0, configuration_done_response, is_json=True)

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
        frame_id = arguments.frameId
        thread_id = py_db.suspended_frames_manager.get_thread_id_for_variable_reference(
            frame_id)

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
        return NetCommand(CMD_RETURN, 0, response, is_json=True)

    def on_attach_request(self, py_db, request):
        '''
        :param AttachRequest request:
        '''
        self._set_debug_options(py_db, request.arguments.kwargs)
        response = pydevd_base_schema.build_response(request)
        return NetCommand(CMD_RETURN, 0, response, is_json=True)

    def on_pause_request(self, py_db, request):
        '''
        :param PauseRequest request:
        '''
        arguments = request.arguments  # : :type arguments: PauseArguments
        thread_id = arguments.threadId

        self.api.request_suspend_thread(py_db, thread_id=thread_id)

        response = pydevd_base_schema.build_response(request)
        return NetCommand(CMD_RETURN, 0, response, is_json=True)

    def on_continue_request(self, py_db, request):
        '''
        :param ContinueRequest request:
        '''
        arguments = request.arguments  # : :type arguments: ContinueArguments
        thread_id = arguments.threadId

        def on_resumed():
            body = {'allThreadsContinued': thread_id == '*'}
            response = pydevd_base_schema.build_response(request, kwargs={'body': body})
            cmd = NetCommand(CMD_RETURN, 0, response, is_json=True)
            py_db.writer.add_command(cmd)

        # Only send resumed notification when it has actually resumed!
        # (otherwise the user could send a continue, receive the notification and then
        # request a new pause which would be paused without sending any notification as
        # it didn't really run in the first place).
        py_db.threads_suspended_single_notification.add_on_resumed_callback(on_resumed)
        self.api.request_resume_thread(thread_id)

    def on_next_request(self, py_db, request):
        '''
        :param NextRequest request:
        '''
        arguments = request.arguments  # : :type arguments: NextArguments
        thread_id = arguments.threadId

        if py_db.get_use_libraries_filter():
            step_cmd_id = CMD_STEP_OVER_MY_CODE
        else:
            step_cmd_id = CMD_STEP_OVER

        self.api.request_step(py_db, thread_id, step_cmd_id)

        response = pydevd_base_schema.build_response(request)
        return NetCommand(CMD_RETURN, 0, response, is_json=True)

    def on_stepin_request(self, py_db, request):
        '''
        :param StepInRequest request:
        '''
        arguments = request.arguments  # : :type arguments: StepInArguments
        thread_id = arguments.threadId

        if py_db.get_use_libraries_filter():
            step_cmd_id = CMD_STEP_INTO_MY_CODE
        else:
            step_cmd_id = CMD_STEP_INTO

        self.api.request_step(py_db, thread_id, step_cmd_id)

        response = pydevd_base_schema.build_response(request)
        return NetCommand(CMD_RETURN, 0, response, is_json=True)

    def on_stepout_request(self, py_db, request):
        '''
        :param StepOutRequest request:
        '''
        arguments = request.arguments  # : :type arguments: StepOutArguments
        thread_id = arguments.threadId

        if py_db.get_use_libraries_filter():
            step_cmd_id = CMD_STEP_RETURN_MY_CODE
        else:
            step_cmd_id = CMD_STEP_RETURN

        self.api.request_step(py_db, thread_id, step_cmd_id)

        response = pydevd_base_schema.build_response(request)
        return NetCommand(CMD_RETURN, 0, response, is_json=True)

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
        return NetCommand(CMD_RETURN, 0, response, is_json=True)

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
        return NetCommand(CMD_RETURN, 0, set_breakpoints_response, is_json=True)

    def on_stacktrace_request(self, py_db, request):
        '''
        :param StackTraceRequest request:
        '''
        # : :type stack_trace_arguments: StackTraceArguments
        stack_trace_arguments = request.arguments
        thread_id = stack_trace_arguments.threadId

        fmt = stack_trace_arguments.format
        if hasattr(fmt, 'to_dict'):
            fmt = fmt.to_dict()
        self.api.request_stack(py_db, request.seq, thread_id, fmt)

    def on_scopes_request(self, py_db, request):
        '''
        Scopes are the top-level items which appear for a frame (so, we receive the frame id
        and provide the scopes it has).

        :param ScopesRequest request:
        '''
        frame_id = request.arguments.frameId

        variables_reference = frame_id
        scopes = [Scope('Locals', int(variables_reference), False).to_dict()]
        body = ScopesResponseBody(scopes)
        scopes_response = pydevd_base_schema.build_response(request, kwargs={'body':body})
        return NetCommand(CMD_RETURN, 0, scopes_response, is_json=True)

    def on_evaluate_request(self, py_db, request):
        '''
        :param EvaluateRequest request:
        '''
        # : :type arguments: EvaluateArguments
        arguments = request.arguments

        thread_id = py_db.suspended_frames_manager.get_thread_id_for_variable_reference(
            arguments.frameId)

        self.api.request_exec_or_evaluate_json(
            py_db, request, thread_id)

    def on_setexpression_request(self, py_db, request):
        # : :type arguments: SetExpressionArguments
        arguments = request.arguments

        thread_id = py_db.suspended_frames_manager.get_thread_id_for_variable_reference(
            arguments.frameId)

        self.api.request_set_expression_json(
            py_db, request, thread_id)

    def on_variables_request(self, py_db, request):
        '''
        Variables can be asked whenever some place returned a variables reference (so, it
        can be a scope gotten from on_scopes_request, the result of some evaluation, etc.).

        Note that in the DAP the variables reference requires a unique int... the way this works for
        pydevd is that an instance is generated for that specific variable reference and we use its
        id(instance) to identify it to make sure all items are unique (and the actual {id->instance}
        is added to a dict which is only valid while the thread is suspended and later cleared when
        the related thread resumes execution).

        see: SuspendedFramesManager

        :param VariablesRequest request:
        '''
        arguments = request.arguments  # : :type arguments: VariablesArguments
        variables_reference = arguments.variablesReference

        thread_id = py_db.suspended_frames_manager.get_thread_id_for_variable_reference(
            variables_reference)
        if thread_id is not None:
            self.api.request_get_variable_json(py_db, request, thread_id)
        else:
            variables = []
            body = VariablesResponseBody(variables)
            variables_response = pydevd_base_schema.build_response(request, kwargs={'body':body})
            return NetCommand(CMD_RETURN, 0, variables_response, is_json=True)

    def on_setvariable_request(self, py_db, request):
        arguments = request.arguments  # : :type arguments: SetVariableArguments
        variables_reference = arguments.variablesReference

        thread_id = py_db.suspended_frames_manager.get_thread_id_for_variable_reference(
            variables_reference)
        if thread_id is not None:
            self.api.request_change_variable_json(py_db, request, thread_id)
        else:
            body = SetVariableResponseBody('')
            variables_response = pydevd_base_schema.build_response(
                request,
                kwargs={
                    'body':body,
                    'success': False,
                    'message': 'Unable to find thread to evaluate variable reference.'
            })
            return NetCommand(CMD_RETURN, 0, variables_response, is_json=True)

    def on_modules_request(self, py_db, request):
        modules_manager = py_db.cmd_factory.modules_manager  # : :type modules_manager: ModulesManager
        modules_info = modules_manager.get_modules_info()
        body = ModulesResponseBody(modules_info)
        variables_response = pydevd_base_schema.build_response(request, kwargs={'body':body})
        return NetCommand(CMD_RETURN, 0, variables_response, is_json=True)

    def on_source_request(self, py_db, request):
        '''
        :param SourceRequest request:
        '''
        source_reference = request.arguments.sourceReference
        server_filename = None
        content = None

        if source_reference != 0:
            server_filename = pydevd_file_utils.get_server_filename_from_source_reference(source_reference)
            if server_filename:
                # Try direct file access first - it's much faster when available.
                try:
                    with open(server_filename, 'r') as stream:
                        content = stream.read()
                except:
                    pass

                if content is None:
                    # File might not exist at all, or we might not have a permission to read it,
                    # but it might also be inside a zipfile, or an IPython cell. In this case,
                    # linecache might still be able to retrieve the source.
                    lines = (linecache.getline(server_filename, i) for i in itertools.count(1))
                    lines = itertools.takewhile(bool, lines)  # empty lines are '\n', EOF is ''

                    # If we didn't get at least one line back, reset it to None so that it's
                    # reported as error below, and not as an empty file.
                    content = ''.join(lines) or None

        body = SourceResponseBody(content or '')
        response_args = {'body': body}

        if content is None:
            if server_filename:
                message = 'Unable to retrieve source for %s' % (server_filename,)
            else:
                message = 'Invalid sourceReference %d' % (source_reference,)
            response_args.update({'success': False, 'message': message})

        response = pydevd_base_schema.build_response(request, kwargs=response_args)
        return NetCommand(CMD_RETURN, 0, response, is_json=True)


process_net_command_json = _PyDevJsonCommandProcessor(pydevd_base_schema.from_json).process_net_command_json
