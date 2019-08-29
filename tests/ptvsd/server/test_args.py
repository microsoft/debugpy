# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import pytest

from tests import debug
from tests.patterns import some


@pytest.mark.parametrize("run_as", ["program", "module", "code"])
def test_args(pyfile, start_method, run_as):
    @pyfile
    def code_to_debug():
        from debug_me import backchannel
        import sys
        backchannel.send(sys.argv)

    with debug.Session(start_method, backchannel=True) as session:
        expected = ["--arg1", "arg2", "-arg3", "--", "arg4", "-a"]
        session.configure(
            run_as, code_to_debug,
            args=expected
        )
        session.start_debugging()

        argv = session.backchannel.receive()
        assert argv == [some.str] + expected
