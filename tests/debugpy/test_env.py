# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, division, print_function, unicode_literals

import os
import pytest
import sys

from tests import debug
from tests.debug import runners


@pytest.mark.parametrize("new_value", [None, "42"])
@pytest.mark.parametrize("case", ["match_case", "mismatch_case"])
@pytest.mark.parametrize("run", runners.all_launch)
def test_env_replace_var(pyfile, target, run, case, new_value):
    @pyfile
    def code_to_debug():
        import os

        import debuggee
        from debuggee import backchannel

        debuggee.setup()
        backchannel.send(dict(os.environ))

    varname = "DEBUGPY_DUMMY_ENV_VAR"

    with debug.Session() as session:
        backchannel = session.open_backchannel()
        session.config.env[varname if case == "match_case" else varname.lower()] = new_value

        os.environ[varname] = "1"
        try:
            with run(session, target(code_to_debug)):
                pass
        finally:
            del os.environ[varname]

        env = backchannel.receive()
        if case == "match_case":
            # If case matches, debug config should replace global env var regardless
            # of the platform.
            if new_value is None:
                assert varname not in env
            else:
                assert env[varname] == "42"
        elif sys.platform == "win32":
            # On Win32, variable names are case-insensitive, so debug config should
            # replace the global env var even if there is a case mismatch.
            if new_value is None:
                assert varname not in env
            else:
                assert env[varname] == "42"
            assert varname.lower() not in env
        else:
            # On other platforms, variable names are case-sensitive, so case mismatch
            # should result in two different variables.
            assert env[varname] == "1"
            if new_value is None:
                assert varname.lower() not in env
            else:
                assert env[varname.lower()] == "42"
