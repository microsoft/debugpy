# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, division, print_function, unicode_literals

"""Global server options that are set via command line, environment variables,
or configuration files.
"""

target_kind = None
"""One of: None, 'file', 'module', 'code', or 'pid'.
"""

target = None
"""Specifies what to debug.

If target_kind is None, then target is None, indicating that the current process
is the one that is initiating debugger attach to itself.

If target_kind is 'file', then target is a path to the file to run.

If target_kind is 'module', then target is the qualified name of the module to run.

If target_kind is 'code', then target is the code to run.

If target_kind is 'pid', then target is the process ID to attach to.
"""

host = "127.0.0.1"
"""Name or IP address of the network interface used by ptvsd.server. If runing in server
mode, this is the interface on which it listens for incoming connections. If running
in client mode, this is the interface to which it connects.
"""

port = 5678
"""Port number used by ptvsd.server. If running in server mode, this is the port on which it
listens for incoming connections. If running in client mode, this is port to which it
connects.
"""

client = False
"""If True, this instance of ptvsd is operating in client mode - i.e. it connects
to the IDE, instead of waiting for an incoming connection from the IDE.
"""

wait = False
"""If True, wait until the debugger is connected before running any code."
"""

multiprocess = True
"""Whether this ptvsd instance is running in multiprocess mode, detouring creation
of new processes and enabling debugging for them.
"""

client_access_token = None
"""Access token to authenticate with the adapter."""
