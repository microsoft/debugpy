# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import pytest
import sys

import ptvsd
from ptvsd.common import log
from tests import debug
from tests.patterns import some


@pytest.fixture
def expected_system_info():
    def version_str(v):
        return "%d.%d.%d%s%d" % (v.major, v.minor, v.micro, v.releaselevel, v.serial)

    try:
        impl_name = sys.implementation.name
    except AttributeError:
        impl_name = ""

    try:
        impl_version = version_str(sys.implementation.version)
    except AttributeError:
        impl_version = ""

    return some.dict.containing(
        {
            "ptvsd": some.dict.containing({"version": ptvsd.__version__}),
            "python": some.dict.containing(
                {
                    "version": version_str(sys.version_info),
                    "implementation": some.dict.containing(
                        {
                            "name": impl_name,
                            "version": impl_version,
                            "description": some.str,
                        }
                    ),
                }
            ),
            "platform": some.dict.containing({"name": sys.platform}),
            "process": some.dict.containing(
                {
                    "pid": some.int,
                    "executable": sys.executable,
                    "bitness": 64 if sys.maxsize > 2 ** 32 else 32,
                }
            ),
        }
    )


def test_ptvsd_systemInfo(pyfile, target, run, expected_system_info):
    @pyfile
    def code_to_debug():
        from debug_me import ptvsd

        ptvsd.break_into_debugger()
        print()

    with debug.Session() as session:
        with run(session, target(code_to_debug)):
            pass

        session.wait_for_stop()

        system_info = session.request("ptvsd_systemInfo")
        log.info("Expected system info: {0}", expected_system_info)
        assert system_info == expected_system_info

        session.request_continue()
