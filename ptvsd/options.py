# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import


"""ptvsd command-line options that need to be globally available.
"""

client = None
"""If True, this instance of ptvsd is operating in client mode - i.e. it connects
to the IDE, instead of waiting for an incoming connection from the IDE.
"""

host = None
"""Name or IP address of the network interface used by ptvsd. If runing in server
mode, this is the interface on which it listens for incoming connections. If running
in client mode, this is the interface to which it connects.
"""

port = None
"""Port number used by ptvsd. If running in server mode, this is the port on which it
listens for incoming connections. If running in client mode, this is port to which it
connects.
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
