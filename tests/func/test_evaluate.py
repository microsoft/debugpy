# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

import sys

from tests.helpers import get_marked_line_numbers, print
from tests.helpers.pattern import ANY
from tests.helpers.session import DebugSession


def test_variables_and_evaluate(pyfile, run_as, start_method):

    @pyfile
    def code_to_debug():
        from dbgimporter import import_and_enable_debugger
        import_and_enable_debugger()
        a = 1
        b = {"one": 1, "two": 2}
        c = 3
        print([a, b, c])

    bp_line = 6
    bp_file = code_to_debug

    with DebugSession() as session:
        session.initialize(
            target=(run_as, bp_file),
            start_method=start_method,
        )
        session.set_breakpoints(bp_file, [bp_line])
        session.start_debugging()
        hit = session.wait_for_thread_stopped()

        resp_scopes = session.send_request('scopes', arguments={
            'frameId': hit.frame_id,
        }).wait_for_response()
        scopes = resp_scopes.body['scopes']
        assert len(scopes) > 0

        resp_variables = session.send_request('variables', arguments={
            'variablesReference': scopes[0]['variablesReference']
        }).wait_for_response()
        variables = list(v for v in resp_variables.body['variables'] if v['name'] in ['a', 'b', 'c'])
        assert len(variables) == 3

        # variables should be sorted alphabetically
        assert ['a', 'b', 'c'] == list(v['name'] for v in variables)

        # get contents of 'b'
        resp_b_variables = session.send_request('variables', arguments={
            'variablesReference': variables[1]['variablesReference']
        }).wait_for_response()
        b_variables = resp_b_variables.body['variables']
        assert len(b_variables) == 3
        assert b_variables[0] == {
            'type': 'int',
            'value': '1',
            'name': ANY.such_that(lambda x: x.find('one') > 0),
            'evaluateName': "b['one']"
        }
        assert b_variables[1] == {
            'type': 'int',
            'value': '2',
            'name': ANY.such_that(lambda x: x.find('two') > 0),
            'evaluateName': "b['two']"
        }
        assert b_variables[2] == {
            'type': 'int',
            'value': '2',
            'name': '__len__',
            'evaluateName': "len(b)"
        }

        # simple variable
        resp_evaluate1 = session.send_request('evaluate', arguments={
            'expression': 'a', 'frameId': hit.frame_id,
        }).wait_for_response()
        assert resp_evaluate1.body == ANY.dict_with({
            'type': 'int',
            'result': '1'
        })

        # dict variable
        resp_evaluate2 = session.send_request('evaluate', arguments={
            'expression': 'b["one"]', 'frameId': hit.frame_id,
        }).wait_for_response()
        assert resp_evaluate2.body == ANY.dict_with({
            'type': 'int',
            'result': '1'
        })

        # expression evaluate
        resp_evaluate3 = session.send_request('evaluate', arguments={
            'expression': 'a + b["one"]', 'frameId': hit.frame_id,
        }).wait_for_response()
        assert resp_evaluate3.body == ANY.dict_with({
            'type': 'int',
            'result': '2'
        })

        session.send_request('continue').wait_for_response(freeze=False)
        session.wait_for_exit()


def test_set_variable(pyfile, run_as, start_method):

    @pyfile
    def code_to_debug():
        import backchannel
        from dbgimporter import import_and_enable_debugger
        import_and_enable_debugger()
        import ptvsd
        a = 1
        ptvsd.break_into_debugger()
        backchannel.write_json(a)

    with DebugSession() as session:
        session.initialize(
            target=(run_as, code_to_debug),
            start_method=start_method,
            use_backchannel=True,
        )
        session.start_debugging()
        hit = session.wait_for_thread_stopped()

        resp_scopes = session.send_request('scopes', arguments={
            'frameId': hit.frame_id
        }).wait_for_response()
        scopes = resp_scopes.body['scopes']
        assert len(scopes) > 0

        resp_variables = session.send_request('variables', arguments={
            'variablesReference': scopes[0]['variablesReference']
        }).wait_for_response()
        variables = list(v for v in resp_variables.body['variables'] if v['name'] == 'a')
        assert len(variables) == 1
        assert variables[0] == {
            'type': 'int',
            'value': '1',
            'name': 'a',
            'evaluateName': "a"
        }

        resp_set_variable = session.send_request('setVariable', arguments={
            'variablesReference': scopes[0]['variablesReference'],
            'name': 'a',
            'value': '1000'
        }).wait_for_response()
        assert resp_set_variable.body == ANY.dict_with({
            'type': 'int',
            'value': '1000'
        })

        session.send_request('continue').wait_for_response(freeze=False)

        assert session.read_json() == 1000

        session.wait_for_exit()


def test_variable_sort(pyfile, run_as, start_method):

    @pyfile
    def code_to_debug():
        from dbgimporter import import_and_enable_debugger
        import_and_enable_debugger()
        b_test = {"spam": "A", "eggs": "B", "abcd": "C"}  # noqa
        _b_test = 12  # noqa
        __b_test = 13  # noqa
        __b_test__ = 14  # noqa
        a_test = 1  # noqa
        _a_test = 2  # noqa
        __a_test = 3  # noqa
        __a_test__ = 4  # noqa
        c_test = {1: "one", 2: "two", 10: "ten"}  # noqa
        _c_test = 22  # noqa
        __c_test = 23  # noqa
        __c_test__ = 24  # noqa
        d = 3  # noqa
        print('done')

    bp_line = 15
    bp_file = code_to_debug

    with DebugSession() as session:
        session.initialize(
            target=(run_as, bp_file),
            start_method=start_method,
        )
        session.set_breakpoints(bp_file, [bp_line])
        session.start_debugging()
        hit = session.wait_for_thread_stopped()

        resp_scopes = session.send_request('scopes', arguments={
            'frameId': hit.frame_id
        }).wait_for_response()
        scopes = resp_scopes.body['scopes']
        assert len(scopes) > 0

        resp_variables = session.send_request('variables', arguments={
            'variablesReference': scopes[0]['variablesReference']
        }).wait_for_response()
        variable_names = list(
            v['name']
            for v in resp_variables.body['variables']
            if v['name'].find('_test') > 0
        )
        assert variable_names == [
                'a_test', 'b_test', 'c_test', '_a_test', '_b_test', '_c_test',
                '__a_test', '__b_test', '__c_test', '__a_test__', '__b_test__',
                '__c_test__'
            ]

        # ensure string dict keys are sorted
        b_test_variable = list(v for v in resp_variables.body['variables'] if v['name'] == 'b_test')
        assert len(b_test_variable) == 1
        resp_dict_variables = session.send_request('variables', arguments={
            'variablesReference': b_test_variable[0]['variablesReference']
        }).wait_for_response()
        variable_names = list(v['name'][1:5] for v in resp_dict_variables.body['variables'])
        assert len(variable_names) == 4
        assert variable_names[:3] == ['abcd', 'eggs', 'spam']

        # ensure numeric dict keys are sorted
        c_test_variable = list(v for v in resp_variables.body['variables'] if v['name'] == 'c_test')
        assert len(c_test_variable) == 1
        resp_dict_variables2 = session.send_request('variables', arguments={
            'variablesReference': c_test_variable[0]['variablesReference']
        }).wait_for_response()
        variable_names = list(v['name'] for v in resp_dict_variables2.body['variables'])
        assert len(variable_names) == 4
        # NOTE: this is commented out due to sorting bug #213
        # assert variable_names[:3] == ['1', '2', '10']

        session.send_request('continue').wait_for_response(freeze=False)
        session.wait_for_exit()


def test_return_values(pyfile, run_as, start_method):

    @pyfile
    def code_to_debug():
        from dbgimporter import import_and_enable_debugger
        import_and_enable_debugger()

        class MyClass(object):

            def do_something(self):
                return 'did something'

        def my_func():
            return 'did more things'

        MyClass().do_something()  # @bp
        my_func()
        print('done')

    line_numbers = get_marked_line_numbers(code_to_debug)
    print(line_numbers)

    expected1 = ANY.dict_with({
        'name': '(return) MyClass.do_something',
        'value': "'did something'",
        'type': 'str',
        'presentationHint': ANY.dict_with({
            'attributes': ANY.such_that(lambda x: 'readOnly' in x)
        }),
    })

    expected2 = ANY.dict_with({
        'name': '(return) my_func',
        'value': "'did more things'",
        'type': 'str',
        'presentationHint': ANY.dict_with({
            'attributes': ANY.such_that(lambda x: 'readOnly' in x)
        }),
    })

    with DebugSession() as session:
        session.initialize(
            target=(run_as, code_to_debug),
            start_method=start_method,
            debug_options=['ShowReturnValue'],
        )
        session.set_breakpoints(code_to_debug, [line_numbers['bp']])
        session.start_debugging()
        hit = session.wait_for_thread_stopped()

        session.send_request('next', {'threadId': hit.thread_id}).wait_for_response()
        hit = session.wait_for_thread_stopped(reason='step')

        resp_scopes = session.send_request('scopes', arguments={
            'frameId': hit.frame_id
        }).wait_for_response()
        scopes = resp_scopes.body['scopes']
        assert len(scopes) > 0

        resp_variables = session.send_request('variables', arguments={
            'variablesReference': scopes[0]['variablesReference']
        }).wait_for_response()
        variables = list(
            v for v in resp_variables.body['variables']
            if v['name'].startswith('(return)')
        )

        assert variables == [expected1]

        session.send_request('next', {'threadId': hit.thread_id}).wait_for_response()
        hit = session.wait_for_thread_stopped(reason='step')

        # Scope should not have changed so use the same scope
        resp_variables = session.send_request('variables', arguments={
            'variablesReference': scopes[0]['variablesReference']
        }).wait_for_response()
        variables = list(
            v for v in resp_variables.body['variables']
            if v['name'].startswith('(return)')
        )

        assert variables == [expected1, expected2]

        session.send_request('continue').wait_for_response()
        session.wait_for_exit()


def test_unicode(pyfile, run_as, start_method):
    # On Python 3, variable names can contain Unicode characters.
    # On Python 2, they must be ASCII, but using a Unicode character in an expression should not crash debugger.

    @pyfile
    def code_to_debug():
        from dbgimporter import import_and_enable_debugger
        import_and_enable_debugger()
        import ptvsd
        # Since Unicode variable name is a SyntaxError at parse time in Python 2,
        # this needs to do a roundabout way of setting it to avoid parse issues.
        globals()[u'\u16A0'] = 123
        ptvsd.break_into_debugger()
        print('break')

    with DebugSession() as session:
        session.initialize(
            target=(run_as, code_to_debug),
            start_method=start_method,
        )
        session.start_debugging()
        hit = session.wait_for_thread_stopped()

        resp_eval = session.send_request('evaluate', arguments={
            'expression': '\u16A0', 'frameId': hit.frame_id,
        }).wait_for_response()

        if sys.version_info >= (3,):
            assert resp_eval.body == ANY.dict_with({
                'type': 'int',
                'result': '123'
            })
        else:
            assert resp_eval.body == ANY.dict_with({
                'type': 'SyntaxError'
            })

        session.send_request('continue').wait_for_response(freeze=False)
        session.wait_for_exit()


def test_hex_numbers(pyfile, run_as, start_method):

    @pyfile
    def code_to_debug():
        from dbgimporter import import_and_enable_debugger
        import_and_enable_debugger()
        a = 100
        b = [1, 10, 100]
        c = {10: 10, 100: 100, 1000: 1000}
        d = {(1, 10, 100): (10000, 100000, 100000)}
        print((a, b, c, d))  # @bp

    line_numbers = get_marked_line_numbers(code_to_debug)
    print(line_numbers)

    with DebugSession() as session:
        session.initialize(
            target=(run_as, code_to_debug),
            start_method=start_method,
        )
        session.set_breakpoints(code_to_debug, [line_numbers['bp']])
        session.start_debugging()
        hit = session.wait_for_thread_stopped()

        resp_scopes = session.send_request('scopes', arguments={
            'frameId': hit.frame_id
        }).wait_for_response()
        scopes = resp_scopes.body['scopes']
        assert len(scopes) > 0

        resp_variables = session.send_request('variables', arguments={
            'variablesReference': scopes[0]['variablesReference'],
            'format': {'hex': True}
        }).wait_for_response()
        variables = list(v for v in resp_variables.body['variables']
                         if v['name'] in ('a', 'b', 'c', 'd'))
        a, b, c, d = sorted(variables, key=lambda v: v['name'])
        assert a == ANY.dict_with({
            'name': 'a',
            'value': "0x64",
            'type': 'int',
            'evaluateName': 'a'
        })

        assert b == ANY.dict_with({
            'name': 'b',
            'value': "[0x1, 0xa, 0x64]",
            'type': 'list',
            'evaluateName': 'b',
            'variablesReference': ANY.dap_id,
        })

        resp_variables = session.send_request('variables', arguments={
            'variablesReference': b['variablesReference'],
            'format': {'hex': True}
        }).wait_for_response()
        b_children = resp_variables.body['variables']
        assert b_children == [
            {'name': '0x0', 'value': '0x1', 'type': 'int', 'evaluateName': 'b[0]'},
            {'name': '0x1', 'value': '0xa', 'type': 'int', 'evaluateName': 'b[1]'},
            {'name': '0x2', 'value': '0x64', 'type': 'int', 'evaluateName': 'b[2]'},
            {'name': '__len__', 'value': '0x3', 'type': 'int', 'evaluateName': 'len(b)'},
        ]

        assert c == ANY.dict_with({
            'name': 'c',
            'value': '{0xa: 0xa, 0x64: 0x64, 0x3e8: 0x3e8}',
            'type': 'dict',
            'evaluateName': 'c',
            'variablesReference': ANY.dap_id,
        })

        resp_variables = session.send_request('variables', arguments={
            'variablesReference': c['variablesReference'],
            'format': {'hex': True}
        }).wait_for_response()
        c_children = resp_variables.body['variables']
        assert c_children == [
            {'name': '0x3e8', 'value': '0x3e8', 'type': 'int', 'evaluateName': 'c[1000]'},
            {'name': '0x64', 'value': '0x64', 'type': 'int', 'evaluateName': 'c[100]'},
            {'name': '0xa', 'value': '0xa', 'type': 'int', 'evaluateName': 'c[10]'},
            {'name': '__len__', 'value': '0x3', 'type': 'int', 'evaluateName': 'len(c)'}
        ]

        assert d == ANY.dict_with({
            'name': 'd',
            'value': '{(0x1, 0xa, 0x64): (0x2710, 0x186a0, 0x186a0)}',
            'type': 'dict',
            'evaluateName': 'd',
            'variablesReference': ANY.dap_id,
        })
        resp_variables = session.send_request('variables', arguments={
            'variablesReference': d['variablesReference'],
            'format': {'hex': True}
        }).wait_for_response()
        d_children = resp_variables.body['variables']
        assert d_children == [
            {'name': '(0x1, 0xa, 0x64)', 'value': '(0x2710, 0x186a0, 0x186a0)', 'type': 'tuple', 'evaluateName': 'd[(1, 10, 100)]', 'variablesReference': ANY.dap_id},
            {'name': '__len__', 'value': '0x1', 'type': 'int', 'evaluateName': 'len(d)'}
        ]

        resp_variables = session.send_request('variables', arguments={
            'variablesReference': d_children[0]['variablesReference'],
            'format': {'hex': True}
        }).wait_for_response()
        d_child_of_child = resp_variables.body['variables']
        assert d_child_of_child == [
            {'name': '0x0', 'value': '0x2710', 'type': 'int', 'evaluateName': 'd[(1, 10, 100)][0]'},
            {'name': '0x1', 'value': '0x186a0', 'type': 'int', 'evaluateName': 'd[(1, 10, 100)][1]'},
            {'name': '0x2', 'value': '0x186a0', 'type': 'int', 'evaluateName': 'd[(1, 10, 100)][2]'},
            {'name': '__len__', 'value': '0x3', 'type': 'int', 'evaluateName': 'len(d[(1, 10, 100)])'}
        ]

        session.send_request('continue').wait_for_response(freeze=False)
        session.wait_for_exit()
