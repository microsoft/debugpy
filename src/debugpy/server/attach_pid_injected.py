# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, division, print_function, unicode_literals

import os


__file__ = os.path.abspath(__file__)
_debugpy_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))


def attach(host, port, client, log_dir=None, client_access_token=None):
    try:
        import sys

        if "threading" not in sys.modules:
            try:

                def on_warn(msg):
                    print(msg, file=sys.stderr)

                def on_exception(msg):
                    print(msg, file=sys.stderr)

                def on_critical(msg):
                    print(msg, file=sys.stderr)

                pydevd_attach_to_process_path = os.path.join(
                    _debugpy_dir,
                    "debugpy",
                    "_vendored",
                    "pydevd",
                    "pydevd_attach_to_process",
                )
                assert os.path.exists(pydevd_attach_to_process_path)
                sys.path.insert(0, pydevd_attach_to_process_path)

                # NOTE: that it's not a part of the pydevd PYTHONPATH
                import attach_script

                attach_script.fix_main_thread_id(
                    on_warn=on_warn, on_exception=on_exception, on_critical=on_critical
                )

                # NOTE: At this point it should be safe to remove this.
                sys.path.remove(pydevd_attach_to_process_path)
            except:
                import traceback

                traceback.print_exc()
                raise

        sys.path.insert(0, _debugpy_dir)
        import debugpy

        # NOTE: Don't do sys.path.remove here it will remove all instances of that path
        # and the user may have set that to debugpy path via PYTHONPATH
        assert sys.path[0] == _debugpy_dir
        del sys.path[0]

        from debugpy.common import log
        from debugpy.server import options

        import pydevd

        py_db = pydevd.get_global_debugger()
        if py_db is not None:
            py_db.dispose_and_kill_all_pydevd_threads(wait=False)

        if log_dir is not None:
            log.log_dir = log_dir
        options.client = client
        options.host = host
        options.port = port
        options.client_access_token = client_access_token

        if options.client:
            debugpy.attach((options.host, options.port))
        else:
            debugpy.enable_attach((options.host, options.port))

        from debugpy.common import log

        log.info("Debugger successfully injected")

    except:
        import traceback

        traceback.print_exc()
        raise log.exception()
