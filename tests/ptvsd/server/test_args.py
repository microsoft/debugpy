# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import pytest

from tests import debug


@pytest.mark.parametrize('run_as', ['file', 'module', 'code'])
def test_args(pyfile, start_method, run_as):
    @pyfile
    def code_to_debug():
        import debug_me  # noqa
        import sys

        print(sys.argv)
        assert sys.argv[1] == '--arg1'
        assert sys.argv[2] == 'arg2'
        assert sys.argv[3] == '-arg3'

    args = ['--arg1', 'arg2', '-arg3']
    with debug.Session() as session:
        session.initialize(
            target=(run_as, code_to_debug),
            start_method=start_method,
            program_args=args
        )
        session.start_debugging()

        session.wait_for_exit()
