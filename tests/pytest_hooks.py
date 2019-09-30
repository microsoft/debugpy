# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import os
import pytest
import pytest_timeout
import sys

from ptvsd.common import fmt, log, options
from tests import pydevd_log


def pytest_addoption(parser):
    parser.addoption(
        "--ptvsd-logs",
        action="store_true",
        help="Write ptvsd and pydevd logs under {rootdir}/tests/_logs/",
    )


def pytest_configure(config):
    if config.option.ptvsd_logs:
        bits = 64 if sys.maxsize > 2 ** 32 else 32
        ver = fmt("{0}.{1}-{bits}", *sys.version_info, bits=bits)
        options.log_dir = (config.rootdir / "tests" / "_logs" / ver).strpath
        log.info("ptvsd and pydevd logs will be under {0}", options.log_dir)


def pytest_report_header(config):
    log.describe_environment(fmt("Test environment for tests-{0}", os.getpid()))


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item, call):
    # Adds attributes setup_report, call_report, and teardown_report to the item,
    # referencing TestReport instances for the corresponding phases, after the scope
    # finished running its tests. This can be used in function-level fixtures to
    # detect test failures, e.g.:
    #
    #   if request.node.call_report.failed: ...

    outcome = yield
    report = outcome.get_result()
    setattr(item, report.when + "_report", report)


def pytest_make_parametrize_id(config, val):
    return getattr(val, "pytest_id", None)


# If a test times out and pytest tries to print the stacks of where it was hanging,
# we want to print the pydevd log as well. This is not a normal pytest hook - we
# just detour pytest_timeout.dump_stacks directly.
_dump_stacks = pytest_timeout.dump_stacks
pytest_timeout.dump_stacks = lambda: (_dump_stacks(), pydevd_log.dump("timed out"))
