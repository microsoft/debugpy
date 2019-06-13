# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

import sys
import ptvsd
from tests.helpers import get_marked_line_numbers
from tests.helpers.session import DebugSession
from tests.helpers.pattern import ANY


def _generate_system_info():
    def version_str(v):
        return '%d.%d.%d%s%d' % (
            v.major,
            v.minor,
            v.micro,
            v.releaselevel,
            v.serial)

    try:
        impl_name = sys.implementation.name
    except AttributeError:
        impl_name = ''

    try:
        impl_version = version_str(sys.implementation.version)
    except AttributeError:
        impl_version = ''

    return ANY.dict_with({
        'ptvsd': {
            'version': ptvsd.__version__,
        },
        'python': {
            'version': version_str(sys.version_info),
            'implementation': {
                'name': impl_name,
                'version': impl_version,
                'description': ANY.str,
            },
        },
        'platform': {
            'name': sys.platform,
        },
        'process': {
            'pid': ANY.int,
            'executable': sys.executable,
            'bitness': 64 if sys.maxsize > 2 ** 32 else 32,
        },
    })


def test_ptvsd_systeminfo(pyfile, run_as, start_method):

    @pyfile
    def code_to_debug():
        from dbgimporter import import_and_enable_debugger
        import_and_enable_debugger()
        a = 'hello' # @bp1
        print(a)

    line_numbers = get_marked_line_numbers(code_to_debug)
    with DebugSession() as session:
        session.initialize(
            target=(run_as, code_to_debug),
            start_method=start_method,
        )

        session.set_breakpoints(code_to_debug, [line_numbers['bp1']])
        session.start_debugging()

        session.wait_for_thread_stopped()

        resp = session.send_request('ptvsd_systemInfo').wait_for_response()
        expected = _generate_system_info()
        assert resp.body == expected

        session.send_request('continue').wait_for_response(freeze=False)
        session.wait_for_exit()
