# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import sys
import ptvsd
from tests import debug
from tests.patterns import some


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

    return some.dict_with({
        'ptvsd': {
            'version': ptvsd.__version__,
        },
        'python': {
            'version': version_str(sys.version_info),
            'implementation': {
                'name': impl_name,
                'version': impl_version,
                'description': some.str,
            },
        },
        'platform': {
            'name': sys.platform,
        },
        'process': {
            'pid': some.int,
            'executable': sys.executable,
            'bitness': 64 if sys.maxsize > 2 ** 32 else 32,
        },
    })


def test_ptvsd_systeminfo(pyfile, run_as, start_method):
    @pyfile
    def code_to_debug():
        import debug_me # noqa
        a = 'hello' # @bp1
        print(a)

    with debug.Session(start_method) as session:
        session.configure(run_as, code_to_debug)

        session.set_breakpoints(code_to_debug, [code_to_debug.lines['bp1']])
        session.start_debugging()

        session.wait_for_stop()

        resp = session.send_request('ptvsd_systemInfo').wait_for_response()
        expected = _generate_system_info()
        assert resp.body == expected

        session.request_continue()
