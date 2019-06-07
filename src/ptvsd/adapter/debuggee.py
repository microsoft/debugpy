# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import atexit


terminate_at_exit = True
"""Whether the debuggee process should be terminated when the adapter process exits,
or allowed to continue running.
"""


def launch_and_connect(request):
    """Launch the process as requested by the DAP "launch" request, with the debug
    server running inside the process; and connect to that server.
    """

    raise NotImplementedError


def terminate(after=0):
    """Terminate the debuggee process, if it is still alive after the specified time.
    """

    pass  # TODO


def _atexit_handler():
    if terminate_at_exit:
        terminate()


atexit.register(_atexit_handler)
