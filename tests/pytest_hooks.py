# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import os
import pytest
import pytest_timeout
import sys

from debugpy.common import log
import tests
from tests import logs


def pytest_addoption(parser):
    parser.addoption(
        "--debugpy-log-dir",
        type=str,
        help="Write debugpy and pydevd logs to the specified directory",
    )
    parser.addoption(
        "--debugpy-log-passed",
        action="store_true",
        help="Keep debugpy and pydevd logs for tests that passed",
    )


def pytest_configure(config):
    if config.option.debugpy_log_dir:
        log.log_dir = config.option.debugpy_log_dir
    else:
        bits = 64 if sys.maxsize > 2**32 else 32
        ver = "{0}.{1}-{bits}".format(*sys.version_info, bits=bits)
        log.log_dir = (tests.root / "_logs" / ver).strpath
    log.info("debugpy and pydevd logs will be under {0}", log.log_dir)


def pytest_report_header(config):
    log.describe_environment(f"Test environment for tests-{os.getpid()}")


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
pytest_timeout.dump_stacks = lambda: (_dump_stacks(), logs.dump())
