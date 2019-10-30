# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, division, print_function, unicode_literals

import pytest

from tests import debug
from tests.debug import targets
from tests.patterns import some


@pytest.mark.parametrize("target", targets.all)
def test_args(pyfile, target, run):
    @pyfile
    def code_to_debug():
        from debug_me import backchannel
        import sys

        backchannel.send(sys.argv)

    args = ["--arg1", "arg2", "-arg3", "--", "arg4", "-a"]

    with debug.Session() as session:
        backchannel = session.open_backchannel()
        with run(session, target(code_to_debug, args=args)):
            pass
        argv = backchannel.receive()
        assert argv == [some.str] + args
