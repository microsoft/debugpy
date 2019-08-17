# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import os
import pytest
import pytest_timeout

from ptvsd.common import fmt, log
from tests import debug, pydevd_log


def pytest_addoption(parser):
    parser.addoption(
        "--ptvsd-logs",
        action="store_true",
        help="Write ptvsd logs to {rootdir}/tests/_logs/",
    )
    parser.addoption(
        "--pydevd-logs",
        action="store_true",
        help="Write pydevd logs to {rootdir}/tests/_logs/",
    )


def pytest_configure(config):
    log_dir = config.rootdir / "tests" / "_logs"
    if True or config.option.ptvsd_logs:
        log.info("ptvsd logs will be in {0}", log_dir)
        debug.PTVSD_ENV["PTVSD_LOG_DIR"] = str(log_dir)
    if config.option.pydevd_logs:
        log.info("pydevd logs will be in {0}", log_dir)
        debug.PTVSD_ENV["PYDEVD_DEBUG"] = "True"
        debug.PTVSD_ENV["PYDEVD_DEBUG_FILE"] = str(log_dir / "pydevd.log")


def pytest_report_header(config):
    log.describe_environment(fmt("Test environment for tests-{0}", os.getpid()))


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item, call):
    # Adds attributes such as setup_result, call_result etc to the item after the
    # corresponding scope finished running its tests. This can be used in function-level
    # fixtures to detect failures, e.g.:
    #
    #   if request.node.call_result.failed: ...

    outcome = yield
    result = outcome.get_result()
    setattr(item, result.when + "_result", result)


# If a test times out and pytest tries to print the stacks of where it was hanging,
# we want to print the pydevd log as well. This is not a normal pytest hook - we
# just detour pytest_timeout.dump_stacks directly.
_dump_stacks = pytest_timeout.dump_stacks
pytest_timeout.dump_stacks = lambda: (_dump_stacks(), pydevd_log.dump("timed out"))
