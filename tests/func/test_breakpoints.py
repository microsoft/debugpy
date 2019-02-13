# -*- coding: utf-8 -*-
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

import os.path
import platform
import pytest
import re
import sys

from tests.helpers import get_marked_line_numbers
from tests.helpers.pathutils import get_test_root
from tests.helpers.session import DebugSession
from tests.helpers.timeline import Event
from tests.helpers.pattern import ANY, Path


BP_TEST_ROOT = get_test_root('bp')


def test_path_with_ampersand(run_as, start_method):
    bp_line = 4
    testfile = os.path.join(BP_TEST_ROOT, 'a&b', 'test.py')

    with DebugSession() as session:
        session.initialize(
            target=(run_as, testfile),
            start_method=start_method,
            ignore_unobserved=[Event('continued')],
        )
        session.set_breakpoints(testfile, [bp_line])
        session.start_debugging()
        hit = session.wait_for_thread_stopped('breakpoint')
        frames = hit.stacktrace.body['stackFrames']
        assert frames[0]['source']['path'] == Path(testfile)

        session.send_request('continue').wait_for_response(freeze=False)
        session.wait_for_exit()


@pytest.mark.skipif(sys.version_info < (3, 0), reason='Paths are not Unicode in Python 2.7')
@pytest.mark.skipif(
    platform.system() == 'Windows' and sys.version_info < (3, 6),
    reason='https://github.com/Microsoft/ptvsd/issues/1124#issuecomment-459506802')
def test_path_with_unicode(run_as, start_method):
    bp_line = 6
    testfile = os.path.join(BP_TEST_ROOT, u'ನನ್ನ_ಸ್ಕ್ರಿಪ್ಟ್.py')

    with DebugSession() as session:
        session.initialize(
            target=(run_as, testfile),
            start_method=start_method,
            ignore_unobserved=[Event('continued')],
        )
        session.set_breakpoints(testfile, [bp_line])
        session.start_debugging()
        hit = session.wait_for_thread_stopped('breakpoint')
        frames = hit.stacktrace.body['stackFrames']
        assert frames[0]['source']['path'] == Path(testfile)
        assert u'ಏನಾದರೂ_ಮಾಡು' == frames[0]['name']

        session.send_request('continue').wait_for_response(freeze=False)
        session.wait_for_exit()


@pytest.mark.parametrize('condition_key', [
    'condition_var',
    'hitCondition_#',
    'hitCondition_eq',
    'hitCondition_gt',
    'hitCondition_ge',
    'hitCondition_lt',
    'hitCondition_le',
    'hitCondition_mod',
])
def test_conditional_breakpoint(pyfile, run_as, start_method, condition_key):
    @pyfile
    def code_to_debug():
        from dbgimporter import import_and_enable_debugger
        import_and_enable_debugger()
        for i in range(0, 10):
            print(i)

    expected = {
        'condition_var': ('condition', 'i==5', '5', 1),
        'hitCondition_#': ('hitCondition', '5', '4', 1),
        'hitCondition_eq': ('hitCondition', '==5', '4', 1),
        'hitCondition_gt': ('hitCondition', '>5', '5', 5),
        'hitCondition_ge': ('hitCondition', '>=5', '4', 6),
        'hitCondition_lt': ('hitCondition', '<5', '0', 4),
        'hitCondition_le': ('hitCondition', '<=5', '0', 5),
        'hitCondition_mod': ('hitCondition', '%3', '2', 3),
    }
    condition_type, condition, value, hits = expected[condition_key]

    bp_line = 4
    with DebugSession() as session:
        session.initialize(
            target=(run_as, code_to_debug),
            start_method=start_method,
            ignore_unobserved=[Event('continued')],
        )
        session.send_request('setBreakpoints', arguments={
            'source': {'path': code_to_debug},
            'breakpoints': [{'line': bp_line, condition_type: condition}],
        }).wait_for_response()
        session.start_debugging()
        hit = session.wait_for_thread_stopped()
        frames = hit.stacktrace.body['stackFrames']
        assert bp_line == frames[0]['line']

        resp_scopes = session.send_request('scopes', arguments={
            'frameId': hit.frame_id
        }).wait_for_response()
        scopes = resp_scopes.body['scopes']
        assert len(scopes) > 0

        resp_variables = session.send_request('variables', arguments={
            'variablesReference': scopes[0]['variablesReference']
        }).wait_for_response()
        variables = list(v for v in resp_variables.body['variables']
                         if v['name'] == 'i')
        assert variables == [
            ANY.dict_with({'name': 'i', 'type': 'int', 'value': value, 'evaluateName': 'i'})
        ]

        session.send_request('continue').wait_for_response(freeze=False)
        for i in range(1, hits):
            session.wait_for_thread_stopped()
            session.send_request('continue').wait_for_response(freeze=False)
        session.wait_for_exit()


def test_crossfile_breakpoint(pyfile, run_as, start_method):
    @pyfile
    def script1():
        from dbgimporter import import_and_enable_debugger  # noqa
        def do_something():
            print('do something')

    @pyfile
    def script2():
        from dbgimporter import import_and_enable_debugger
        import_and_enable_debugger()
        import script1
        script1.do_something()
        print('Done')

    bp_script1_line = 3
    bp_script2_line = 4
    with DebugSession() as session:
        session.initialize(
            target=(run_as, script2),
            start_method=start_method,
            ignore_unobserved=[Event('continued')],
        )
        session.set_breakpoints(script1, lines=[bp_script1_line])
        session.set_breakpoints(script2, lines=[bp_script2_line])
        session.start_debugging()

        hit = session.wait_for_thread_stopped()
        frames = hit.stacktrace.body['stackFrames']
        assert bp_script2_line == frames[0]['line']
        assert frames[0]['source']['path'] == Path(script2)

        session.send_request('continue').wait_for_response(freeze=False)
        hit = session.wait_for_thread_stopped()
        frames = hit.stacktrace.body['stackFrames']
        assert bp_script1_line == frames[0]['line']
        assert frames[0]['source']['path'] == Path(script1)

        session.send_request('continue').wait_for_response(freeze=False)
        session.wait_for_exit()


@pytest.mark.parametrize('error_name', [
    'NameError',
    'OtherError',
])
def test_error_in_condition(pyfile, run_as, start_method, error_name):
    @pyfile
    def code_to_debug():
        from dbgimporter import import_and_enable_debugger
        import_and_enable_debugger()
        def do_something_bad():
            raise ArithmeticError()
        for i in range(1, 10):
            pass

    # NOTE: NameError in condition, is a special case. Pydevd is configured to skip
    # traceback for name errors. See https://github.com/Microsoft/ptvsd/issues/853
    # for more details. For all other errors we should be printing traceback.
    condition = {
        'NameError': ('x==5'),  # 'x' does not exist in the debuggee
        'OtherError': ('do_something_bad()==5')  # throws some error
    }

    bp_line = 5
    with DebugSession() as session:
        session.initialize(
            target=(run_as, code_to_debug),
            start_method=start_method,
            ignore_unobserved=[Event('continued')],
        )
        session.send_request('setBreakpoints', arguments={
            'source': {'path': code_to_debug},
            'breakpoints': [{
                'line': bp_line,
                'condition': condition[error_name],
            }],
        }).wait_for_response()
        session.start_debugging()

        session.wait_for_exit()
        assert session.get_stdout_as_string() == b''
        if error_name == 'NameError':
            assert session.get_stderr_as_string().find(b'NameError') == -1
        else:
            assert session.get_stderr_as_string().find(b'ArithmeticError') > 0


def test_log_point(pyfile, run_as, start_method):
    @pyfile
    def code_to_debug():
        from dbgimporter import import_and_enable_debugger
        import_and_enable_debugger()
        a = 10
        for i in range(1, a):
            print('value: %d' % i)
        # Break at end too so that we're sure we get all output
        # events before the break.
        a = 10

    bp_line = 5
    end_bp_line = 8
    with DebugSession() as session:
        session.initialize(
            target=(run_as, code_to_debug),
            start_method=start_method,
            ignore_unobserved=[Event('continued')],
        )
        session.send_request('setBreakpoints', arguments={
            'source': {'path': code_to_debug},
            'breakpoints': [{
                'line': bp_line,
                'logMessage': 'log: {a + i}'
            }, {'line': end_bp_line}],
        }).wait_for_response()
        session.start_debugging()

        # Breakpoint at the end just to make sure we get all output events.
        hit = session.wait_for_thread_stopped()
        frames = hit.stacktrace.body['stackFrames']
        assert end_bp_line == frames[0]['line']

        session.send_request('continue').wait_for_response(freeze=False)

        session.wait_for_exit()
        assert session.get_stderr_as_string() == b''

        output = session.all_occurrences_of(Event('output', ANY.dict_with({'category': 'stdout'})))
        output_str = ''.join(o.body['output'] for o in output)
        logged = sorted(int(i) for i in re.findall(r"log:\s([0-9]*)", output_str))
        values = sorted(int(i) for i in re.findall(r"value:\s([0-9]*)", output_str))

        assert logged == list(range(11, 20))
        assert values == list(range(1, 10))


def test_condition_with_log_point(pyfile, run_as, start_method):
    @pyfile
    def code_to_debug():
        from dbgimporter import import_and_enable_debugger
        import_and_enable_debugger()
        a = 10
        for i in range(1, a):
            print('value: %d' % i)
        # Break at end too so that we're sure we get all output
        # events before the break.
        a = 10

    bp_line = 5
    end_bp_line = 8
    with DebugSession() as session:
        session.initialize(
            target=(run_as, code_to_debug),
            start_method=start_method,
            ignore_unobserved=[Event('continued')],
        )
        session.send_request('setBreakpoints', arguments={
            'source': {'path': code_to_debug},
            'breakpoints': [{
                'line': bp_line,
                'logMessage': 'log: {a + i}',
                'condition': 'i==5'
            }, {'line': end_bp_line}],
        }).wait_for_response()
        session.start_debugging()
        hit = session.wait_for_thread_stopped()
        frames = hit.stacktrace.body['stackFrames']
        assert bp_line == frames[0]['line']

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
            if v['name'] == 'i'
        )
        assert variables == [
            ANY.dict_with({'name': 'i', 'type': 'int', 'value': '5', 'evaluateName': 'i'})
        ]

        session.send_request('continue').wait_for_response(freeze=False)

        # Breakpoint at the end just to make sure we get all output events.
        hit = session.wait_for_thread_stopped()
        frames = hit.stacktrace.body['stackFrames']
        assert end_bp_line == frames[0]['line']
        session.send_request('continue').wait_for_response(freeze=False)

        session.wait_for_exit()
        assert session.get_stderr_as_string() == b''

        output = session.all_occurrences_of(Event('output', ANY.dict_with({'category': 'stdout'})))
        output_str = ''.join(o.body['output'] for o in output)
        logged = sorted(int(i) for i in re.findall(r"log:\s([0-9]*)", output_str))
        values = sorted(int(i) for i in re.findall(r"value:\s([0-9]*)", output_str))

        assert logged == list(range(11, 20))
        assert values == list(range(1, 10))


def test_package_launch():
    bp_line = 2
    cwd = get_test_root('testpkgs')
    testfile = os.path.join(cwd, 'pkg1', '__main__.py')

    with DebugSession() as session:
        session.initialize(
            target=('module', 'pkg1'),
            start_method='launch',
            ignore_unobserved=[Event('continued')],
            cwd=cwd,
        )
        session.set_breakpoints(testfile, [bp_line])
        session.start_debugging()

        hit = session.wait_for_thread_stopped()
        frames = hit.stacktrace.body['stackFrames']
        assert bp_line == frames[0]['line']

        session.send_request('continue').wait_for_response(freeze=False)
        session.wait_for_exit()


def test_add_and_remove_breakpoint(pyfile, run_as, start_method):
    @pyfile
    def code_to_debug():
        from dbgimporter import import_and_enable_debugger
        import_and_enable_debugger()
        for i in range(0, 10):
            print(i)
        import backchannel
        backchannel.read_json()

    bp_line = 4
    with DebugSession() as session:
        session.initialize(
            target=(run_as, code_to_debug),
            start_method=start_method,
            ignore_unobserved=[Event('continued')],
            use_backchannel=True,
        )
        session.set_breakpoints(code_to_debug, [bp_line])
        session.start_debugging()

        hit = session.wait_for_thread_stopped()
        frames = hit.stacktrace.body['stackFrames']
        assert bp_line == frames[0]['line']

        # remove breakpoints in file
        session.set_breakpoints(code_to_debug, [])
        session.send_request('continue').wait_for_response(freeze=False)

        session.write_json('done')
        session.wait_for_next(Event('output', ANY.dict_with({'category': 'stdout', 'output': '9'})))
        session.wait_for_exit()

        output = session.all_occurrences_of(Event('output', ANY.dict_with({'category': 'stdout'})))
        output = sorted(int(o.body['output'].strip()) for o in output if len(o.body['output'].strip()) > 0)
        assert list(range(0, 10)) == output


def test_invalid_breakpoints(pyfile, run_as, start_method):
    @pyfile
    def code_to_debug():
        from dbgimporter import import_and_enable_debugger
        import_and_enable_debugger()

        b = True
        while b:        #@bp1-expected
            pass        #@bp1-requested
            break

        print()         #@bp2-expected
        [               #@bp2-requested
            1, 2, 3,    #@bp3-expected
        ]               #@bp3-requested

        # Python 2.7 only.
        print()         #@bp4-expected
        print(1,        #@bp4-requested-1
              2, 3,     #@bp4-requested-2
              4, 5, 6)

    line_numbers = get_marked_line_numbers(code_to_debug)
    from tests.helpers import print
    print(line_numbers)

    with DebugSession() as session:
        session.initialize(
            target=(run_as, code_to_debug),
            start_method=start_method,
            ignore_unobserved=[Event('continued')],
        )

        requested_bps = [
            line_numbers['bp1-requested'],
            line_numbers['bp2-requested'],
            line_numbers['bp3-requested'],
        ]
        if sys.version_info < (3,):
            requested_bps += [
                line_numbers['bp4-requested-1'],
                line_numbers['bp4-requested-2'],
            ]

        actual_bps = session.set_breakpoints(code_to_debug, requested_bps)
        actual_bps = [bp['line'] for bp in actual_bps]

        expected_bps = [
            line_numbers['bp1-expected'],
            line_numbers['bp2-expected'],
            line_numbers['bp3-expected'],
        ]
        if sys.version_info < (3,):
            expected_bps += [
                line_numbers['bp4-expected'],
                line_numbers['bp4-expected'],
            ]

        assert expected_bps == actual_bps

        # Now let's make sure that we hit all of the expected breakpoints,
        # and stop where we expect them to be.

        session.start_debugging()

        # If there's multiple breakpoints on the same line, we only stop once,
        # so remove duplicates first.
        expected_bps = sorted(set(expected_bps))

        while expected_bps:
            hit = session.wait_for_thread_stopped()
            frames = hit.stacktrace.body['stackFrames']
            line = frames[0]['line']
            assert line == expected_bps[0]
            del expected_bps[0]
            session.send_request('continue').wait_for_response()
        assert not expected_bps

        session.wait_for_exit()
