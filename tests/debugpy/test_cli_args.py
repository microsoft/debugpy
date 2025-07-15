# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from tests import debug


def test_cli_options_with_no_debugger():
    import debugpy

    cli_options = debugpy.get_cli_options()
    assert cli_options is None


def test_cli_options_under_file_connect(pyfile, target, run):
    @pyfile
    def code_to_debug():
        import dataclasses
        import debugpy

        import debuggee
        from debuggee import backchannel

        debuggee.setup()
        backchannel.send(dataclasses.asdict(debugpy.get_cli_options()))

    with debug.Session() as session:
        backchannel = session.open_backchannel()

        with run(session, target(code_to_debug)):
            pass

        cli_options = backchannel.receive()
        assert cli_options['mode'] == 'connect'
        assert cli_options['target_kind'] == 'file'
