# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import os
import pytest
import shutil
import sys
import traceback

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

        backchannel.send({"ide_os": pydevd_file_utils._ide_os})
        print("done")  # @break_here

    with debug.Session() as session:
        backchannel = session.setup_backchannel()
        session.initialize(
            target=(run_as, code_to_debug),
            start_method=start_method,
            use_backchannel=True,
            path_mappings=[
                {
                    "localRoot": "C:\\TEMP\\src",
                    "remoteRoot": os.path.dirname(code_to_debug),
                }
            ],
        )
        if invalid_os_type:
            session.debug_options.append("CLIENT_OS_TYPE=INVALID")
        session.set_breakpoints(
            "c:\\temp\\src\\" + os.path.basename(code_to_debug),
            [code_to_debug.lines["break_here"]],
        )
        session.start_debugging()
        hit = session.wait_for_stop("breakpoint")
        assert hit.frames[0]["source"]["path"] == "C:\\TEMP\\src\\" + os.path.basename(
            code_to_debug
        )

        json_read = backchannel.receive()
        assert json_read == {"ide_os": "WINDOWS"}

        session.request_continue()
        session.wait_for_exit()


def test_with_dot_remote_root(pyfile, tmpdir, start_method, run_as):
    @pyfile
    def code_to_debug():
        from debug_me import backchannel
        import os

        backchannel.send(os.path.abspath(__file__))
        print("done")  # @bp

    path_local = tmpdir.mkdir("local").join("code_to_debug.py").strpath
    path_remote = tmpdir.mkdir("remote").join("code_to_debug.py").strpath

    dir_local = os.path.dirname(path_local)
    dir_remote = os.path.dirname(path_remote)

    shutil.copyfile(code_to_debug, path_local)
    shutil.copyfile(code_to_debug, path_remote)

    with debug.Session() as session:
        backchannel = session.setup_backchannel()
        session.initialize(
            target=(run_as, path_remote),
            start_method=start_method,
            use_backchannel=True,
            path_mappings=[{"localRoot": dir_local, "remoteRoot": "."}],
            cwd=dir_remote,
        )
        session.set_breakpoints(path_remote, [code_to_debug["bp"]])
        session.start_debugging()
        hit = session.wait_for_stop("breakpoint")
        print("Local Path: " + path_local)
        print("Frames: " + str(hit.frames))
        assert hit.frames[0]["source"]["path"] == some.path(path_local)

        remote_code_path = backchannel.receive()
        assert path_remote == some.path(remote_code_path)

        session.request_continue()
        session.wait_for_exit()


def test_with_path_mappings(pyfile, tmpdir, start_method, run_as):
    @pyfile
    def code_to_debug():
        from debug_me import backchannel
        import os
        import sys

        json = backchannel.receive()
        call_me_back_dir = json["call_me_back_dir"]
        sys.path.append(call_me_back_dir)

        import call_me_back

        def call_func():
            print("break here")  # @bp

        backchannel.send(os.path.abspath(__file__))
        call_me_back.call_me_back(call_func)
        print("done")

    path_local = tmpdir.mkdir("local").join("code_to_debug.py").strpath
    path_remote = tmpdir.mkdir("remote").join("code_to_debug.py").strpath

    dir_local = os.path.dirname(path_local)
    dir_remote = os.path.dirname(path_remote)

    shutil.copyfile(code_to_debug, path_local)
    shutil.copyfile(code_to_debug, path_remote)

    call_me_back_dir = test_data / "call_me_back"

    with debug.Session() as session:
        backchannel = session.setup_backchannel()
        session.initialize(
            target=(run_as, path_remote),
            start_method=start_method,
            use_backchannel=True,
            path_mappings=[{"localRoot": dir_local, "remoteRoot": dir_remote}],
        )
        session.set_breakpoints(path_remote, [code_to_debug.lines["bp"]])
        session.start_debugging()
        backchannel.send({"call_me_back_dir": call_me_back_dir})
        hit = session.wait_for_stop("breakpoint")

        assert hit.frames[0]["source"]["path"] == some.path(path_local)
        source_reference = hit.frames[0]["source"]["sourceReference"]
        assert source_reference == 0  # Mapped files should be found locally.

        assert hit.frames[1]["source"]["path"].endswith("call_me_back.py")
        source_reference = hit.frames[1]["source"]["sourceReference"]
        assert source_reference > 0  # Unmapped file should have a source reference.

        resp_source = session.send_request(
            "source", arguments={"sourceReference": 0}
        ).wait_for_response(raise_if_failed=False)
        assert not resp_source.success
        text = "".join(
            traceback.format_exception_only(type(resp_source.body), resp_source.body)
        )
        assert "Source unavailable" in text

        resp_source = session.send_request(
            "source", arguments={"sourceReference": source_reference}
        ).wait_for_response()
        assert "def call_me_back(callback):" in (resp_source.body["content"])

        remote_code_path = backchannel.receive()
        assert path_remote == some.path(remote_code_path)

        session.request_continue()
        session.wait_for_exit()
