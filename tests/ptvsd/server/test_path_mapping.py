# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import pytest
import sys

from tests import debug, test_data
from tests.patterns import some


@pytest.mark.skipif(sys.platform == "win32", reason="Linux/Mac only test.")
@pytest.mark.parametrize("invalid_os_type", [True])
def test_client_ide_from_path_mapping_linux_backend(
    pyfile, tmpdir, start_method, run_as, invalid_os_type
):
    """
    Test simulating that the backend is on Linux and the client is on Windows
    (automatically detect it from the path mapping).
    """

    @pyfile
    def code_to_debug():
        from debug_me import backchannel
        import pydevd_file_utils

        backchannel.send(pydevd_file_utils._ide_os)
        print("done")  # @bp

    with debug.Session(start_method) as session:
        backchannel = session.setup_backchannel()
        session.initialize(
            target=(run_as, code_to_debug),
            path_mappings=[
                {
                    "localRoot": "C:\\TEMP\\src",
                    "remoteRoot": code_to_debug.dirname,
                }
            ],
        )
        if invalid_os_type:
            session.debug_options.append("CLIENT_OS_TYPE=INVALID")
        session.set_breakpoints(
            "c:\\temp\\src\\" + code_to_debug.basename,
            [code_to_debug.lines["bp"]],
        )
        session.start_debugging()

        assert backchannel.receive() == "WINDOWS"

        session.wait_for_stop(
            "breakpoint",
            expected_frames=[
                some.dap.frame(
                    some.dap.source("C:\\TEMP\\src\\" + code_to_debug.basename),
                    line=code_to_debug.lines["bp"],
                ),
            ],
        )

        session.request_continue()
        session.wait_for_exit()


def test_with_dot_remote_root(pyfile, tmpdir, start_method, run_as):
    @pyfile
    def code_to_debug():
        from debug_me import backchannel
        import os

        backchannel.send(os.path.abspath(__file__))
        print("done")  # @bp

    path_local = tmpdir.mkdir("local") / "code_to_debug.py"
    path_remote = tmpdir.mkdir("remote") / "code_to_debug.py"

    dir_local = path_local.dirname
    dir_remote = path_remote.dirname

    code_to_debug.copy(path_local)
    code_to_debug.copy(path_remote)

    with debug.Session(start_method) as session:
        backchannel = session.setup_backchannel()
        session.initialize(
            target=(run_as, path_remote),
            cwd=dir_remote,
            path_mappings=[{"localRoot": dir_local, "remoteRoot": "."}],
        )
        session.set_breakpoints(path_local, all)
        session.start_debugging()

        actual_path_remote = backchannel.receive()
        assert some.path(actual_path_remote) == path_remote

        session.wait_for_stop(
            "breakpoint",
            expected_frames=[
                some.dap.frame(
                    some.dap.source(path_local),
                    line="bp",
                ),
            ],
        )

        session.request_continue()
        session.wait_for_exit()


def test_with_path_mappings(pyfile, tmpdir, start_method, run_as):
    @pyfile
    def code_to_debug():
        from debug_me import backchannel
        import os
        import sys

        backchannel.send(os.path.abspath(__file__))
        call_me_back_dir = backchannel.receive()
        sys.path.insert(0, call_me_back_dir)

        import call_me_back

        def call_func():
            print("break here")  # @bp

        call_me_back.call_me_back(call_func)  # @call_me_back
        print("done")

    dir_local = tmpdir.mkdir("local")
    dir_remote = tmpdir.mkdir("remote")

    path_local = dir_local / "code_to_debug.py"
    path_remote = dir_remote / "code_to_debug.py"

    code_to_debug.copy(path_local)
    code_to_debug.copy(path_remote)

    call_me_back_dir = test_data / "call_me_back"
    call_me_back_py = call_me_back_dir / "call_me_back.py"

    with debug.Session(start_method) as session:
        backchannel = session.setup_backchannel()
        session.initialize(
            target=(run_as, path_remote),
            path_mappings=[{"localRoot": dir_local, "remoteRoot": dir_remote}],
        )
        session.set_breakpoints(path_local, ["bp"])
        session.start_debugging()

        actual_path_remote = backchannel.receive()
        assert some.path(actual_path_remote) == path_remote
        backchannel.send(call_me_back_dir)

        stop = session.wait_for_stop(
            "breakpoint",
            expected_frames=[
                some.dap.frame(
                    # Mapped files should not have a sourceReference, so that the IDE
                    # doesn't try to fetch them instead of opening the local file.
                    some.dap.source(path_local, sourceReference=0),
                    line="bp",
                ),
                some.dap.frame(
                    # Unmapped files should have a sourceReference, since there's no
                    # local file for the IDE to open.
                    some.dap.source(call_me_back_py, sourceReference=some.int.not_equal_to(0)),
                    line="callback",

                ),
                some.dap.frame(
                    # Mapped files should not have a sourceReference, so that the IDE
                    # doesn't try to fetch them instead of opening the local file.
                    some.dap.source(path_local, sourceReference=0),
                    line="call_me_back",
                ),
            ],
        )

        srcref = stop.frames[1]["source"]["sourceReference"]

        try:
            session.request("source", {"sourceReference": 0})
        except Exception as ex:
            assert "Source unavailable" in str(ex)
        else:
            pytest.fail("sourceReference=0 should not be valid")

        source = session.request("source", {"sourceReference": srcref})
        assert "def call_me_back(callback):" in source["content"]

        session.request_continue()
        session.wait_for_exit()
