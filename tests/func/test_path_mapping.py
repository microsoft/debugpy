# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

import os
from shutil import copyfile
from tests.helpers.pattern import Path
from tests.helpers.session import DebugSession
from tests.helpers.timeline import Event


def test_with_dot_remote_root(pyfile, tmpdir, run_as, start_method):
    @pyfile
    def code_to_debug():
        from dbgimporter import import_and_enable_debugger
        import_and_enable_debugger()
        import os
        import backchannel
        backchannel.write_json(os.path.abspath(__file__))
        print('done')

    bp_line = 6
    path_local = tmpdir.mkdir('local').join('code_to_debug.py').strpath
    path_remote = tmpdir.mkdir('remote').join('code_to_debug.py').strpath

    dir_local = os.path.dirname(path_local)
    dir_remote = os.path.dirname(path_remote)

    copyfile(code_to_debug, path_local)
    copyfile(code_to_debug, path_remote)

    with DebugSession() as session:
        session.initialize(
            target=(run_as, path_remote),
            start_method=start_method,
            ignore_unobserved=[Event('continued')],
            use_backchannel=True,
            path_mappings=[{
                'localRoot': dir_local,
                'remoteRoot': '.',
            }],
            cwd=dir_remote,
        )
        session.set_breakpoints(path_remote, [bp_line])
        session.start_debugging()
        hit = session.wait_for_thread_stopped('breakpoint')
        frames = hit.stacktrace.body['stackFrames']
        print('Local Path: ' + path_local)
        print('Frames: ' + str(frames))
        assert frames[0]['source']['path'] == Path(path_local)

        remote_code_path = session.read_json()
        assert path_remote == Path(remote_code_path)

        session.send_request('continue').wait_for_response(freeze=False)
        session.wait_for_exit()

def test_with_path_mappings(pyfile, tmpdir, run_as, start_method):
    @pyfile
    def code_to_debug():
        from dbgimporter import import_and_enable_debugger
        import_and_enable_debugger()
        import os
        import backchannel
        backchannel.write_json(os.path.abspath(__file__))
        print('done')

    bp_line = 6
    path_local = tmpdir.mkdir('local').join('code_to_debug.py').strpath
    path_remote = tmpdir.mkdir('remote').join('code_to_debug.py').strpath

    dir_local = os.path.dirname(path_local)
    dir_remote = os.path.dirname(path_remote)

    copyfile(code_to_debug, path_local)
    copyfile(code_to_debug, path_remote)

    with DebugSession() as session:
        session.initialize(
            target=(run_as, path_remote),
            start_method=start_method,
            ignore_unobserved=[Event('continued')],
            use_backchannel=True,
            path_mappings=[{
                'localRoot': dir_local,
                'remoteRoot': dir_remote,
            }],
        )
        session.set_breakpoints(path_remote, [bp_line])
        session.start_debugging()
        hit = session.wait_for_thread_stopped('breakpoint')
        frames = hit.stacktrace.body['stackFrames']
        assert frames[0]['source']['path'] == Path(path_local)

        remote_code_path = session.read_json()
        assert path_remote == Path(remote_code_path)

        session.send_request('continue').wait_for_response(freeze=False)
        session.wait_for_exit()
