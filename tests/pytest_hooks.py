# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import multiprocessing
import os
from os import path
import pytest
import pytest_timeout
import site  # noqa
import sys
import sysconfig
import threading  # noqa

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
    result = [fmt("Test environment for tests-{0}:\n\n", os.getpid())]

    def report(*args, **kwargs):
        result.append(fmt(*args, **kwargs))

    def report_paths(expr, label=None):
        prefix = fmt("    {0}: ", label or expr)

        try:
            paths = expr() if callable(expr) else eval(expr, globals())
        except AttributeError:
            report("{0}<missing>\n", prefix)
            return

        if not isinstance(paths, (list, tuple)):
            paths = [paths]

        for p in sorted(paths):
            report("{0}{1}", prefix, p)
            rp = path.realpath(p)
            if p != rp:
                report("({0})", rp)
            report("\n")

            prefix = " " * len(prefix)

    report("CPU count: {0}\n\n", multiprocessing.cpu_count())
    report("System paths:\n")
    report_paths("sys.prefix")
    report_paths("sys.base_prefix")
    report_paths("sys.real_prefix")
    report_paths("site.getsitepackages()")
    report_paths("site.getusersitepackages()")

    site_packages = [
        p for p in sys.path
        if os.path.exists(p) and os.path.basename(p) == 'site-packages'
    ]
    report_paths(lambda: site_packages, "sys.path (site-packages)")

    for name in sysconfig.get_path_names():
        expr = fmt("sysconfig.get_path({0!r})", name)
        report_paths(expr)

    report_paths("os.__file__")
    report_paths("threading.__file__")

    result = "".join(result).rstrip("\n")
    log.info("{0}", result)


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item, call):
    # Adds attributes such as setup_result, call_result etc to the item after the
    # corresponding scope finished running its tests. This can be used in function-level
    # fixtures to detect failures, e.g.:
    #
    #   if request.node.call_result.failed: ...

    outcome = yield
    result = outcome.get_result()
    setattr(item, result.when + '_result', result)


# If a test times out and pytest tries to print the stacks of where it was hanging,
# we want to print the pydevd log as well. This is not a normal pytest hook - we
# just detour pytest_timeout.dump_stacks directly.
_dump_stacks = pytest_timeout.dump_stacks
pytest_timeout.dump_stacks = lambda: (_dump_stacks(), pydevd_log.dump("timed out"))
