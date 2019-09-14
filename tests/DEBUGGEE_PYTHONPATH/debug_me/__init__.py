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


# Used by backchannel.
session_id = int(os.getenv("PTVSD_TEST_SESSION_ID"))
name = "Debuggee-" + str(session_id)


# For non-blocking communication between the test and the debuggee. The debuggee
# can access this as a normal dict - scratchpad["foo"] etc. The test should assign
# to session.scratchpad[...], which will automatically perform "evaluate" requests
# as needed to assign the value.
scratchpad = {}


# Some runners require code to be executed in the debuggee process, either to set up
# the debug server, or to ensure that it doesn't run any other code until the debugger
# is attached. This provides a facility to inject such code.
_code = os.environ.pop("PTVSD_TEST_DEBUG_ME", None)
if _code:
    _code = compile(_code, "<PTVSD_TEST_DEBUG_ME>", "exec")
    eval(_code, {})


# For `from debug_me import ...`.
import ptvsd
import ptvsd.server
import pydevd
