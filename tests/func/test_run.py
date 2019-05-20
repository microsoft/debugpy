# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

import os
import pytest
import re

import ptvsd

from tests.helpers import print
from tests.helpers.pathutils import get_test_root
from tests.helpers.pattern import ANY, Regex
from tests.helpers.session import DebugSession
from tests.helpers.timeline import Event


@pytest.mark.parametrize('run_as', ['file', 'module', 'code'])
def test_run(pyfile, run_as, start_method):
    @pyfile
    def code_to_debug():
        import os
        import sys
        import backchannel
        from dbgimporter import import_and_enable_debugger
        import_and_enable_debugger()

        print('begin')
        assert backchannel.read_json() == 'continue'
        backchannel.write_json(os.path.abspath(sys.modules['ptvsd'].__file__))
        print('end')

    with DebugSession() as session:
        session.initialize(target=(run_as, code_to_debug), start_method=start_method, use_backchannel=True)
        session.start_debugging()
        assert session.timeline.is_frozen

        process_event, = session.all_occurrences_of(Event('process'))
        assert process_event == Event('process', ANY.dict_with({
            'name': '-c' if run_as == 'code' else Regex(re.escape(code_to_debug) + r'(c|o)?$')
        }))

        session.write_json('continue')
        ptvsd_path = session.read_json()
        expected_ptvsd_path = os.path.abspath(ptvsd.__file__)
        assert re.match(re.escape(expected_ptvsd_path) + r'(c|o)?$', ptvsd_path)

        session.wait_for_exit()


def test_run_submodule():
    cwd = get_test_root('testpkgs')
    with DebugSession() as session:
        session.initialize(
            target=('module', 'pkg1.sub'),
            start_method='launch',
            cwd=cwd,
        )
        session.start_debugging()
        session.wait_for_next(Event('output', ANY.dict_with({'category': 'stdout', 'output': 'three'})))
        session.wait_for_exit()


@pytest.mark.parametrize('run_as', ['file', 'module', 'code'])
def test_nodebug(pyfile, run_as):
    @pyfile
    def code_to_debug():
        # import_and_enable_debugger
        import backchannel
        backchannel.read_json()
        print('ok')

    with DebugSession() as session:
        session.no_debug = True
        session.initialize(target=(run_as, code_to_debug), start_method='launch', use_backchannel=True)
        breakpoints = session.set_breakpoints(code_to_debug, [3, 4])
        assert breakpoints == [{'verified': False}, {'verified': False}]
        session.start_debugging()

        session.write_json(None)

        # Breakpoint shouldn't be hit.
        session.wait_for_exit()

        session.expect_realized(Event('output', ANY.dict_with({
            'category': 'stdout',
            'output': 'ok',
        })))


@pytest.mark.parametrize('run_as', ['script', 'module'])
def test_run_vs(pyfile, run_as):
    @pyfile
    def code_to_debug():
        # import_and_enable_debugger
        import backchannel
        backchannel.write_json('ok')

    @pyfile
    def ptvsd_launcher():
        # import_and_enable_debugger
        import ptvsd.debugger
        import backchannel
        args = tuple(backchannel.read_json())
        print('debug%r' % (args,))
        ptvsd.debugger.debug(*args)

    with DebugSession() as session:
        filename = 'code_to_debug' if run_as == 'module' else code_to_debug
        session.before_connect = lambda: session.write_json([filename, session.ptvsd_port, None, None, run_as])

        session.initialize(target=('file', ptvsd_launcher), start_method='custom_client', use_backchannel=True)
        session.start_debugging()
        assert session.read_json() == 'ok'
        session.wait_for_exit()
