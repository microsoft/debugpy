# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import pytest

from tests import debug


@pytest.mark.parametrize("run_as", ["program", "module", "code"])
def test_with_wait_for_attach(pyfile, start_method, run_as):
    @pyfile
    def code_to_debug():
        # NOTE: These tests verify break_into_debugger for launch
        # and attach cases. For attach this is always after wait_for_attach
        from debug_me import ptvsd

        ptvsd.break_into_debugger()
        print("break here") # @break

    with debug.Session(start_method) as session:
        session.configure(run_as, code_to_debug)
        session.start_debugging()
        hit = session.wait_for_stop()
        assert hit.frames[0]["line"] == code_to_debug.lines["break"]

        session.request_continue()
        session.stop_debugging()


@pytest.mark.parametrize("run_as", ["program", "module", "code"])
@pytest.mark.skip(reason="https://github.com/microsoft/ptvsd/issues/1505")
def test_breakpoint_function(pyfile, start_method, run_as):
    @pyfile
    def code_to_debug():
        # NOTE: These tests verify break_into_debugger for launch
        # and attach cases. For attach this is always after wait_for_attach
        import debug_me  # noqa

        # TODO: use ptvsd.break_into_debugger() on <3.7
        breakpoint()  # noqa
        print("break here") # @break

    with debug.Session(start_method) as session:
        session.configure(run_as, code_to_debug)
        session.start_debugging()
        hit = session.wait_for_stop()
        path = hit.frames[0]["source"]["path"]
        assert path.endswith("code_to_debug.py") or path.endswith("<string>")
        assert hit.frames[0]["line"] == code_to_debug.lines["break"]

        session.request_continue()
        session.stop_debugging()
