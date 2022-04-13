# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

"""The main script for the watchdog worker process.
"""

# This code runs in a separate process, and should not import pytest or tests!
# Do not import debugpy on top level, either - sys.path needs to be fixed first -
# this is done in main().

import collections
import psutil
import sys
import time


ProcessInfo = collections.namedtuple("ProcessInfo", ["process", "name"])


def main(tests_pid):
    from debugpy.common import log, messaging

    # log.stderr_levels |= {"info"}
    log.timestamp_format = "06.3f"
    log_file = log.to_file(prefix="tests.watchdog")

    stream = messaging.JsonIOStream.from_stdio(f"tests-{tests_pid}")
    log.info("Spawned WatchDog-{0} for tests-{0}", tests_pid)
    tests_process = psutil.Process(tests_pid)
    stream.write_json(["watchdog", log_file.filename])

    spawned_processes = {}  # pid -> ProcessInfo
    try:
        stop = False
        while not stop:
            try:
                message = stream.read_json()
            except Exception:
                break

            command = message[0]
            args = message[1:]

            if command == "stop":
                assert not args
                stop = True

            elif command == "register_spawn":
                pid, name = args
                pid = int(pid)

                log.info(
                    "WatchDog-{0} registering spawned process {1} (pid={2})",
                    tests_pid,
                    name,
                    pid,
                )
                try:
                    _, old_name = spawned_processes[pid]
                except KeyError:
                    pass
                else:
                    log.warning(
                        "WatchDog-{0} already tracks a process with pid={1}: {2}",
                        tests_pid,
                        pid,
                        old_name,
                    )
                spawned_processes[pid] = ProcessInfo(psutil.Process(pid), name)

            elif command == "unregister_spawn":
                pid, name = args
                pid = int(pid)

                log.info(
                    "WatchDog-{0} unregistering spawned process {1} (pid={2})",
                    tests_pid,
                    name,
                    pid,
                )
                spawned_processes.pop(pid, None)

            else:
                raise AssertionError(f"Unknown watchdog command: {command!r}")

            stream.write_json(["ok"])

    except Exception as exc:
        stream.write_json(["error", str(exc)])
        log.reraise_exception()

    finally:
        try:
            stream.close()
        except Exception:
            log.swallow_exception()

        # If the test runner becomes a zombie process, it is still considered alive,
        # and wait() will block indefinitely. Poll status instead.
        while True:
            try:
                status = tests_process.status()
            except Exception:
                # If we can't even get its status, assume that it's dead.
                break

            # If it's dead or a zombie, time to clean it up.
            if status in (psutil.STATUS_DEAD, psutil.STATUS_ZOMBIE):
                break

            # Otherwise, let's wait a bit to see if anything changes.
            try:
                tests_process.wait(0.1)
            except Exception:
                pass

        leftover_processes = {proc for proc, _ in spawned_processes.values()}
        for proc, _ in spawned_processes.values():
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
                "WatchDog-{0} killing orphaned test child process (pid={1})",
                tests_pid,
                proc.pid,
            )

            try:
                proc.kill()
            except psutil.NoSuchProcess:
                pass
            except Exception:
                log.swallow_exception()

        log.info("WatchDog-{0} exiting", tests_pid)


if __name__ == "__main__":
    main(int(sys.argv[1]))
