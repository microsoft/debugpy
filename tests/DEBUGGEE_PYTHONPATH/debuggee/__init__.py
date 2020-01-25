# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, division, print_function, unicode_literals

"""Makes sure that the code is run under debugger, using the appropriate method
to establish connection back to DebugSession in the test process, depending on
DebugSession.start_method used by the test.

This module MUST be imported, and setup() must be called, by all test scripts that
are run via debug.Session and the standard runners.
"""

__all__ = ["debugpy", "pydevd", "session_id"]

import os


# Used by backchannel.
session_id = int(os.getenv("DEBUGPY_TEST_SESSION_ID"))
name = "Debuggee-" + str(session_id)


# For non-blocking communication between the test and the debuggee. The debuggee
# can access this as a normal dict - scratchpad["foo"] etc. The test should assign
# to session.scratchpad[...], which will automatically perform "evaluate" requests
# as needed to assign the value.
scratchpad = {}


# Some runners require code to be executed in the debuggee process, either to set up
# the debug server, or to ensure that it doesn't run any other code until the debugger
# is attached. This provides a facility to inject such code.
def setup():
    _code = os.environ.pop("DEBUGPY_TEST_DEBUGGEE_SETUP", None)
    if _code:
        _code = compile(_code, "<DEBUGPY_TEST_DEBUGGEE_SETUP>", "exec")
        eval(_code, {})
