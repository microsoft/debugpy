# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

from tests.helpers.pattern import Path
from tests.helpers.session import DebugSession
from tests.helpers import get_marked_line_numbers
import sys


def test_with_path_mappings(pyfile, tmpdir, run_as, start_method):

    @pyfile
    def code_to_debug():
        from dbgimporter import import_and_enable_debugger
        import_and_enable_debugger()

        def full_function():
            # Note that this function is not called, it's there just to make the mapping explicit.
            print('cell1 line 2')  # @map_to_cell1_line_2
            print('cell1 line 3')  # @map_to_cell1_line_3

            print('cell2 line 2')  # @map_to_cell2_line_2
            print('cell2 line 3')  # @map_to_cell2_line_3

        def strip_lines(s):
            return '\n'.join([line.strip() for line in s.splitlines()])

        def create_code():
            cell1_code = compile(strip_lines(''' # line 1
            a = 1  # line 2
            b = 2  # line 3
            '''), '<cell1>', 'exec')

            cell2_code = compile(strip_lines('''# line 1
            c = 3  # line 2
            d = 4  # line 3
            '''), '<cell2>', 'exec')

            return {'cell1': cell1_code, 'cell2': cell2_code}

        code = create_code()
        exec(code['cell1'], {})
        exec(code['cell1'], {})

        exec(code['cell2'], {})
        exec(code['cell2'], {})
        print('ok')

    with DebugSession() as session:
        session.initialize(
            target=(run_as, code_to_debug),
            start_method=start_method,
        )

        marked_line_numbers = get_marked_line_numbers(code_to_debug)
        map_to_cell_1_line2 = marked_line_numbers['map_to_cell1_line_2']
        map_to_cell_2_line2 = marked_line_numbers['map_to_cell2_line_2']

        source_entry = code_to_debug
        if sys.platform == 'win32':
            # Check if it matches even not normalized.
            source_entry = code_to_debug[0].lower() + code_to_debug[1:].upper()
            source_entry = source_entry.replace('\\', '/')

        # Set breakpoints first and the map afterwards to make sure that it's reapplied.
        session.set_breakpoints(code_to_debug, [map_to_cell_1_line2])

        session.send_request('setPydevdSourceMap', arguments={
            'source': {'path': source_entry},
            'pydevdSourceMaps': [
                {
                    'line': map_to_cell_1_line2,
                    'endLine': map_to_cell_1_line2 + 1,
                    'runtimeSource': {'path': '<cell1>'},
                    'runtimeLine': 2,
                },
                {
                    'line': map_to_cell_2_line2,
                    'endLine': map_to_cell_2_line2 + 1,
                    'runtimeSource': {'path': '<cell2>'},
                    'runtimeLine': 2,
                },
            ],
        }).wait_for_response()

        session.start_debugging()
        hit = session.wait_for_thread_stopped('breakpoint')

        frames = hit.stacktrace.body['stackFrames']
        assert frames[0]['source']['path'] == Path(code_to_debug)

        session.set_breakpoints(code_to_debug, [map_to_cell_2_line2])
        # Leave only the cell2 mapping.
        session.send_request('setPydevdSourceMap', arguments={
            'source': {'path': source_entry},
            'pydevdSourceMaps': [
                {
                    'line': map_to_cell_2_line2,
                    'endLine': map_to_cell_2_line2 + 1,
                    'runtimeSource': {'path': '<cell2>'},
                    'runtimeLine': 2,
                },
            ],
        }).wait_for_response()

        session.send_request('continue').wait_for_response()

        hit = session.wait_for_thread_stopped('breakpoint')

        # Remove the cell2 mapping so that it doesn't stop again.
        session.send_request('setPydevdSourceMap', arguments={
            'source': {'path': source_entry},
            'pydevdSourceMaps': [
                {
                    'line': map_to_cell_1_line2,
                    'endLine': map_to_cell_1_line2 + 1,
                    'runtimeSource': {'path': '<cell1>'},
                    'runtimeLine': 2,
                },
            ],
        }).wait_for_response()

        session.send_request('continue').wait_for_response(freeze=False)
        session.wait_for_exit()
