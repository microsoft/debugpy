import os
import os.path

from tests.helpers.debugsession import Awaitable
from tests.helpers.resource import TestResources
from . import (
    lifecycle_handshake, LifecycleTestsBase, DebugInfo,
)


TEST_FILES = TestResources.from_module(__name__)


class VariableTests(LifecycleTestsBase):

    def test_variables(self):
        filename = TEST_FILES.resolve('simple.py')
        cwd = os.path.dirname(filename)
        self.run_test_variables(DebugInfo(filename=filename, cwd=cwd))

    def run_test_variables(self, debug_info):
        bp_line = 3
        breakpoints = [{
            'source': {
                'path': debug_info.filename
            },
            'breakpoints': [{
                'line': bp_line
            }]
        }]

        with self.start_debugging(debug_info) as dbg:
            session = dbg.session
            with session.wait_for_event('stopped') as result:
                (_, req_launch_attach, _, _, _, _,
                 ) = lifecycle_handshake(session, debug_info.starttype,
                                         breakpoints=breakpoints)
                req_launch_attach.wait()
            event = result['msg']
            tid = event.body['threadId']

            req_stacktrace = session.send_request(
                'stackTrace',
                threadId=tid,
            )
            req_stacktrace.wait()
            frames = req_stacktrace.resp.body['stackFrames']
            frame_id = frames[0]['id']
            req_scopes = session.send_request(
                'scopes',
                frameId=frame_id,
            )
            req_scopes.wait()
            scopes = req_scopes.resp.body['scopes']
            variables_reference = scopes[0]['variablesReference']
            req_variables = session.send_request(
                'variables',
                variablesReference=variables_reference,
            )
            req_variables.wait()
            variables = req_variables.resp.body['variables']

            var_b = list(b for b in variables if b['name'] == 'b')
            var_b = var_b[0] if len(var_b) == 1 else None
            if var_b is None:
                var_b_variables = None
            else:
                var_b_ref = var_b['variablesReference']
                req_variables = session.send_request(
                    'variables',
                    variablesReference=var_b_ref,
                )
                req_variables.wait()
                var_b_variables = req_variables.resp.body['variables']

            req_evaluate1 = session.send_request(
                'evaluate',
                expression='a',
                frameId=frame_id,
            )
            req_evaluate2 = session.send_request(
                'evaluate',
                expression="b['one']",
                frameId=frame_id,
            )
            Awaitable.wait_all(req_evaluate1, req_evaluate2)
            var_a_evaluate = req_evaluate1.resp.body
            var_b_one_evaluate = req_evaluate2.resp.body

            session.send_request('continue', threadId=tid)

        # Variables for a, b, __file__, __main__
        self.assertGreaterEqual(len(variables), 3)
        self.assert_is_subset(variables, [{
            'name': 'a',
            'type': 'int',
            'value': '1',
            'evaluateName': 'a'
        }, {
            'name': 'b',
            'type': 'dict',
            'value': "{'one': 1, 'two': 2}",
            'evaluateName': 'b'
        }, {
            'name': '__builtins__',
            'type': 'dict',
            'evaluateName': '__builtins__'
        }, {
            'name': '__doc__',
            'type': 'NoneType',
            'value': 'None',
            'evaluateName': '__doc__'
        }, {
            'name': '__file__',
            'type': 'str',
            'presentationHint': {
                'attributes': ['rawString']
            },
            'evaluateName': '__file__'
        }, {
            'name': '__loader__',
            'type': 'SourceFileLoader',
            'evaluateName': '__loader__'
        }, {
            'name': '__name__',
            'type': 'str',
            'value': "'__main__'",
            'presentationHint': {
                'attributes': ['rawString']
            },
            'evaluateName': '__name__'
        }, {
            'name': '__package__',
            'type': 'NoneType',
            'value': 'None',
            'evaluateName': '__package__'
        }, {
            'name': '__spec__',
            'type': 'NoneType',
            'value': 'None',
            'evaluateName': '__spec__'
        }])
        self.assertEqual(var_a_evaluate, {
            'type': 'int',
            'result': '1',
        })

        assert var_b_variables is not None
        self.assert_is_subset(var_b_variables, [{
            'type': 'int',
            'value': '1',
            'evaluateName': "b['one']"
        }, {
            'type': 'int',
            'value': '2',
            'evaluateName': "b['two']"
        }, {
            'name': '__len__',
            'type': 'int',
            'value': '2',
            'evaluateName': 'b.__len__'
        }])

        self.assertEqual(var_b_one_evaluate, {
            'type': 'int',
            'result': '1',
        })

    def test_variable_sorting(self):
        filename = TEST_FILES.resolve('for_sorting.py')
        cwd = os.path.dirname(filename)
        self.run_test_variable_sorting(DebugInfo(filename=filename, cwd=cwd))

    def run_test_variable_sorting(self, debug_info):
        bp_line = 16
        breakpoints = [{
            'source': {
                'path': debug_info.filename
            },
            'breakpoints': [{
                'line': bp_line
            }]
        }]

        with self.start_debugging(debug_info) as dbg:
            session = dbg.session
            with session.wait_for_event('stopped') as result:
                (_, req_launch_attach, _, _, _, _,
                 ) = lifecycle_handshake(session, debug_info.starttype,
                                         breakpoints=breakpoints)
                req_launch_attach.wait()

            event = result['msg']
            tid = event.body['threadId']

            req_stacktrace = session.send_request(
                'stackTrace',
                threadId=tid,
            )
            req_stacktrace.wait()
            frames = req_stacktrace.resp.body['stackFrames']
            frame_id = frames[0]['id']
            req_scopes = session.send_request(
                'scopes',
                frameId=frame_id,
            )
            req_scopes.wait()
            scopes = req_scopes.resp.body['scopes']
            variables_reference = scopes[0]['variablesReference']
            req_variables = session.send_request(
                'variables',
                variablesReference=variables_reference,
            )
            req_variables.wait()
            variables = req_variables.resp.body['variables']

            b_dict_vars = list(v for v in variables if v['name'] == 'b_test')
            if not b_dict_vars:
                b_dict_var_items = None
            else:
                b_dict_var, = b_dict_vars
                b_dict_var_ref = b_dict_var['variablesReference']
                req_variables = session.send_request(
                    'variables',
                    variablesReference=b_dict_var_ref,
                )
                req_variables.wait()
                b_dict_var_items = req_variables.resp.body['variables']

            #c_dict_vars = list(v for v in variables if v['name'] == 'c_test')
            #if not c_dict_vars:
            #    c_dict_var_items = None
            #else:
            #    c_dict_var, = c_dict_vars
            #    c_dict_var_ref = c_dict_var['variablesReference']
            #    req_variables = session.send_request(
            #        'variables',
            #        variablesReference=c_dict_var_ref,
            #    )
            #    req_variables.wait()
            #    c_dict_var_items = req_variables.resp.body['variables']

            session.send_request('continue', threadId=tid)

        variables_to_check = list(v['name']
                                  for v in variables
                                  if v['name'].find('_test') > 0)
        expected_var_order = [
            'a_test', 'b_test', 'c_test', '_a_test', '_b_test', '_c_test',
            '__a_test', '__b_test', '__c_test', '__a_test__', '__b_test__',
            '__c_test__'
        ]
        self.assertEqual(expected_var_order, variables_to_check)

        # Dict keys are sorted normally, i.e., the '_' rules don't apply
        # TODO: v['name'][1:5] is needed due to bug #45
        b_dict_var_keys = list(v['name'][1:5]
                               for v in b_dict_var_items
                               if not v['name'].startswith('__'))
        expected_b_dict_var_keys_order = ['abcd', 'eggs', 'spam']
        self.assertEqual(b_dict_var_keys, expected_b_dict_var_keys_order)

        # TODO: Numeric dict keys have following issues
        # bug: #45 and #213
        # c_dict_var_keys = list(v['name'] for v in c_dict_var_items)
        # expected_c_dict_var_keys_order = ['1', '2', '10', '__len__']
        # self.assertEqual(c_dict_var_keys, expected_c_dict_var_keys_order)
