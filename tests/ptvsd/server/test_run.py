# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

from os import path
import pytest
import re

import ptvsd
from tests import debug, test_data
from tests.patterns import some
from tests.timeline import Event


@pytest.mark.parametrize('run_as', ['file', 'module', 'code'])
def test_run(pyfile, start_method, run_as):
    @pyfile
    def code_to_debug():
        from debug_me import backchannel
        from os import path
        import sys

        print('begin')
        assert backchannel.receive() == 'continue'
        backchannel.send(path.abspath(sys.modules['ptvsd'].__file__))
        print('end')

    with debug.Session(start_method) as session:
        backchannel = session.setup_backchannel()
        session.initialize(target=(run_as, code_to_debug))
        session.start_debugging()
        assert session.timeline.is_frozen

        process_event, = session.all_occurrences_of(Event('process'))
        expected_name = (
            '-c' if run_as == 'code'
            else some.str.matching(re.escape(code_to_debug) + r'(c|o)?$')
        )
        assert process_event == Event('process', some.dict.containing({
            'name': expected_name
        }))

        backchannel.send('continue')
        ptvsd_path = backchannel.receive()
        expected_ptvsd_path = path.abspath(ptvsd.__file__)
        assert re.match(re.escape(expected_ptvsd_path) + r'(c|o)?$', ptvsd_path)

        session.wait_for_exit()


def test_run_submodule():
    cwd = str(test_data / 'testpkgs')
    with debug.Session('launch') as session:
        session.initialize(target=('module', 'pkg1.sub'), cwd=cwd)
        session.start_debugging()
        session.wait_for_next(Event('output', some.dict.containing({
            'category': 'stdout',
            'output': 'three'
        })))
        session.wait_for_exit()


@pytest.mark.parametrize('run_as', ['file', 'module', 'code'])
def test_nodebug(pyfile, run_as):
    @pyfile
    def code_to_debug():
        from debug_me import backchannel
        backchannel.receive() #@ bp1
        print('ok')  #@ bp2

    with debug.Session('launch') as session:
        session.no_debug = True
        backchannel = session.setup_backchannel()
        session.initialize(target=(run_as, code_to_debug))

        breakpoints = session.set_breakpoints(code_to_debug, [
            code_to_debug.lines["bp1"],
            code_to_debug.lines["bp2"],
        ])
        assert breakpoints == [
            {'verified': False},
            {'verified': False},
        ]

        session.start_debugging()
        backchannel.send(None)

        # Breakpoint shouldn't be hit.
        session.wait_for_exit()

        session.expect_realized(Event('output', some.dict.containing({
            'category': 'stdout',
            'output': 'ok',
        })))


@pytest.mark.parametrize('run_as', ['script', 'module'])
def test_run_vs(pyfile, run_as):
    @pyfile
    def code_to_debug():
        from debug_me import backchannel
        print('ok')
        backchannel.send('ok')

    @pyfile
    def ptvsd_launcher():
        from debug_me import backchannel
        import ptvsd.debugger

        args = tuple(backchannel.receive())
        print('debug{0!r}'.format(args))
        ptvsd.debugger.debug(*args)

    filename = 'code_to_debug' if run_as == 'module' else code_to_debug
    with debug.Session('custom_client') as session:
        backchannel = session.setup_backchannel()

        session.before_connect = lambda: backchannel.send([
            filename, session.ptvsd_port, None, None, run_as
        ])

        session.initialize(target=('file', ptvsd_launcher))
        session.start_debugging()

        assert backchannel.receive() == 'ok'
        session.wait_for_exit()
