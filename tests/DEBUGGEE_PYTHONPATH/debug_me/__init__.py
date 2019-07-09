# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

"""Makes sure that the code is run under debugger, using the appropriate method
to establish connection back to DebugSession in the test process, depending on
DebugSession.start_method used by the test.

This module MUST be imported by all code that is executed via DebugSession, unless
it is launched with start_method="custom_client", for tests that need to set up
ptvsd and establish the connection themselves in some special manner.

If the code needs to access ptvsd and/or pydevd, this module additionally exports
both as global variables, specifically so that it is possible to write::

    from debug_me import ptvsd, pydevd, backchannel
"""

__all__ = ["ptvsd", "pydevd", "session_id"]

import os

# For `from debug_me import ...`.
import ptvsd
import pydevd


# Used by backchannel.
session_id = int(os.getenv("PTVSD_SESSION_ID"))
name = "ptvsd-" + str(session_id)


# For all start methods except for "attach_socket_import", DebugSession itself
# will take care of starting the debuggee process correctly.
#
# For "attach_socket_import", DebugSession will supply the code that needs to
# be executed in the debuggee to enable debugging and establish connection back
# to DebugSession - the debuggee simply needs to execute it as is.
_code = os.getenv("PTVSD_DEBUG_ME")
if _code:
    _code = compile(_code, "<PTVSD_DEBUG_ME>", "exec")
    eval(_code, {})
