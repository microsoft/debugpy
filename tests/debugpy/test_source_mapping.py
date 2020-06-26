# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, division, print_function, unicode_literals

import pytest
import sys

import tests
from tests import debug
from tests.debug import runners
from tests.patterns import some


if not tests.full:

    @pytest.fixture(params=[runners.launch, runners.attach_connect["cli"]])
    def run(request):
        return request.param


def test_with_path_mappings(pyfile, tmpdir, target, run):
    @pyfile
    def code_to_debug():
        import debuggee

        debuggee.setup()

        def full_function():
            # Note that this function is not called, it's there just to make the mapping explicit.
            print("cell1 line 2")  # @map_to_cell1_line_2
            print("cell1 line 3")  # @map_to_cell1_line_3

            print("cell2 line 2")  # @map_to_cell2_line_2
            print("cell2 line 3")  # @map_to_cell2_line_3

        def strip_lines(s):
            return "\n".join([line.strip() for line in s.splitlines()])

        def create_code():
            cell1_code = compile(
                strip_lines(
                    """ # line 1
            a = 1  # line 2
            b = 2  # line 3
            """
                ),
                "<cell1>",
                "exec",
            )

            cell2_code = compile(
                strip_lines(
                    """# line 1
            c = 3  # line 2
            d = 4  # line 3
            """
                ),
                "<cell2>",
                "exec",
            )

            return {"cell1": cell1_code, "cell2": cell2_code}

        code = create_code()
        exec(code["cell1"], {})
        exec(code["cell1"], {})

        exec(code["cell2"], {})
        exec(code["cell2"], {})
        print("ok")

    with debug.Session() as session:
        map_to_cell_1_line2 = code_to_debug.lines["map_to_cell1_line_2"]
        map_to_cell_2_line2 = code_to_debug.lines["map_to_cell2_line_2"]

        source_entry = code_to_debug.strpath
        if sys.platform == "win32":
            # Check if it matches even not normalized.
            source_entry = source_entry[0].lower() + source_entry[1:].upper()
            source_entry = source_entry.replace("\\", "/")

        with run(session, target(code_to_debug)):
            # Set breakpoints first and the map afterwards to make sure that it's reapplied.
            session.set_breakpoints(code_to_debug, [map_to_cell_1_line2])

            session.request(
                "setPydevdSourceMap",
                {
                    "source": {"path": source_entry},
                    "pydevdSourceMaps": [
                        {
                            "line": map_to_cell_1_line2,
                            "endLine": map_to_cell_1_line2 + 1,
                            "runtimeSource": {"path": "<cell1>"},
                            "runtimeLine": 2,
                        },
                        {
                            "line": map_to_cell_2_line2,
                            "endLine": map_to_cell_2_line2 + 1,
                            "runtimeSource": {"path": "<cell2>"},
                            "runtimeLine": 2,
                        },
                    ],
                },
            )

        session.wait_for_stop(
            "breakpoint",
            expected_frames=[some.dap.frame(code_to_debug, line=map_to_cell_1_line2)],
        )

        session.set_breakpoints(code_to_debug, [map_to_cell_2_line2])
        # Leave only the cell2 mapping.
        session.request(
            "setPydevdSourceMap",
            {
                "source": {"path": source_entry},
                "pydevdSourceMaps": [
                    {
                        "line": map_to_cell_2_line2,
                        "endLine": map_to_cell_2_line2 + 1,
                        "runtimeSource": {"path": "<cell2>"},
                        "runtimeLine": 2,
                    }
                ],
            },
        )

        session.request_continue()
        session.wait_for_stop(
            "breakpoint",
            expected_frames=[some.dap.frame(code_to_debug, line=map_to_cell_2_line2)],
        )

        # Remove the cell2 mapping so that it doesn't stop again.
        session.request(
            "setPydevdSourceMap",
            {
                "source": {"path": source_entry},
                "pydevdSourceMaps": [
                    {
                        "line": map_to_cell_1_line2,
                        "endLine": map_to_cell_1_line2 + 1,
                        "runtimeSource": {"path": "<cell1>"},
                        "runtimeLine": 2,
                    }
                ],
            },
        )

        session.request_continue()
