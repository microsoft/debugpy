# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import


"""ptvsd command-line options that need to be globally available.
"""

code = None
"""When running with -c, specifies the code that needs to be run.
"""


multiprocess = False
"""Whether this ptvsd instance is running in multiprocess mode, detouring creation
of new processes and enabling debugging for them.
"""


subprocess_of = None
"""If not None, the process ID of the parent process (running in multiprocess mode)
that spawned this subprocess.
"""


subprocess_notify = None
"""The port number of the subprocess listener. If specified, a 'ptvsd_subprocess'
notification must be sent to that port once this ptvsd is initialized and ready to
accept a connection from the client.
"""
