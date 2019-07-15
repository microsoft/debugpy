# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

"""The main script for the watchdog worker process.
"""

# This code runs in a separate process, and should not import pytest or tests!
# Do not import ptvsd on top level, either - sys.path needs to be fixed first -
# this is done in main().

import os
import sys
import platform
import psutil
import tempfile
import time


def main(tests_pid):
    # To import ptvsd, the "" entry in sys.path - which is added automatically on
    # Python 2 - must be removed first; otherwise, we end up importing tests/ptvsd.
    if "" in sys.path:
        sys.path.remove("")

    from ptvsd.common import fmt, log, messaging

    log.stderr_levels = set(log.LEVELS)
    log.timestamp_format = "06.3f"
    log.filename_prefix = "watchdog"
    log.to_file()

    stream = messaging.JsonIOStream.from_stdio(fmt("tests-{0}", tests_pid))
    log.info("Spawned watchdog-{0} for tests-{0}", tests_pid)
    tests_process = psutil.Process(tests_pid)
    stream.write_json("ready")

    spawned_processes = {}
    try:
        while True:
            try:
                message = stream.read_json()
            except Exception:
                break

            command, pid, name = message
            pid = int(pid)

            if command == "register_spawn":
                log.debug(
                    "watchdog-{0} registering spawned process {1} (pid={2})",
                    tests_pid,
                    name,
                    pid,
                )
                assert pid not in spawned_processes
                spawned_processes[pid] = psutil.Process(pid)

            elif command == "unregister_spawn":
                log.debug(
                    "watchdog-{0} unregistering spawned process {1} (pid={2})",
                    tests_pid,
                    name,
                    pid,
                )
                spawned_processes.pop(pid, None)

            else:
                raise AssertionError(fmt("Unknown watchdog command: {0!r}", command))

    except Exception:
        raise log.exception()

    finally:
        tests_process.wait()

        leftover_processes = set(spawned_processes.values())
        for proc in spawned_processes.values():
            try:
                leftover_processes |= proc.children(recursive=True)
            except Exception:
                pass

        leftover_processes = {proc for proc in leftover_processes if proc.is_running()}
        if not leftover_processes:
            return

        # Wait a bit to allow the terminal to catch up on the test runner output.
        time.sleep(0.3)

        log.newline(level="warning")
        log.warning(
            "tests-{0} process terminated unexpectedly, and left some orphan child "
            "processes behind: {1!r}",
            tests_pid,
            sorted({proc.pid for proc in leftover_processes}),
        )

        for proc in leftover_processes:
            log.warning(
                "watchdog-{0} killing orphaned test child process (pid={1})",
                tests_pid,
                proc.pid,
            )

            if platform.system() == "Linux":
                try:
                    # gcore will automatically add pid to the filename
                    core_file = os.path.join(tempfile.gettempdir(), "ptvsd_core")
                    gcore_cmd = fmt("gcore -o {0} {1}", core_file, proc.pid)
                    log.warning("{0}", gcore_cmd)
                    os.system(gcore_cmd)
                except Exception:
                    log.exception()

            try:
                proc.kill()
            except psutil.NoSuchProcess:
                pass
            except Exception:
                log.exception()

        log.debug("watchdog-{0} exiting", tests_pid)


if __name__ == "__main__":
    main(int(sys.argv[1]))
