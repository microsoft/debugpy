# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import sys

import pytest

from tests import debug
from tests.debug import runners, targets
from tests.patterns import some

pytestmark = pytest.mark.skipif(
    not hasattr(sys, "set_lazy_imports"),
    reason="PEP 810 lazy imports require Python 3.15+",
)


@pytest.mark.parametrize("run", runners.all)
@pytest.mark.parametrize("target", targets.all_named)
def test_lazy_imports_all(pyfile, target, run):
    @pyfile
    def code_to_debug():
        import sys

        import debuggee
        from debuggee import backchannel

        debuggee.setup()
        backchannel.send(sys.get_lazy_imports())  # @bp

    with debug.Session() as session:
        session.spawn_adapter.env["PYTHON_LAZY_IMPORTS"] = "all"
        env = (
            session.config.env
            if run.request == "launch"
            else session.spawn_debuggee.env
        )
        env["PYTHON_LAZY_IMPORTS"] = "all"

        backchannel = session.open_backchannel()
        with run(session, target(code_to_debug)):
            session.set_breakpoints(code_to_debug, all)

        session.wait_for_stop(
            "breakpoint", expected_frames=[some.dap.frame(code_to_debug, line="bp")]
        )
        session.request_continue()
        assert backchannel.receive() == "all"
