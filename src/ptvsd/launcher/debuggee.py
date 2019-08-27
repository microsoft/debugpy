# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, division, print_function, unicode_literals

import atexit
import locale
import os
import struct
import subprocess
import sys
import threading

from ptvsd.common import fmt, log, messaging


process = None
"""subprocess.Popen instance for the debuggee process."""

wait_on_exit_predicates = []
"""List of functions that determine whether to pause after debuggee process exits.

Every function is invoked with exit code as the argument. If any of the functions
returns True, the launcher pauses and waits for user input before exiting.
"""


def describe():
    return fmt("debuggee process with PID={0}", process.pid)


def spawn(process_name, cmdline, cwd, env, redirect_output):
    from ptvsd.launcher import adapter, output

    log.info(
        "Spawning debuggee process:\n\n"
        "Current directory: {0!j}\n\n"
        "Command line: {1!j}\n\n"
        "Environment variables: {2!j}\n\n",
        cwd,
        cmdline,
        env,
    )

    close_fds = set()
    try:
        if redirect_output:
            # subprocess.PIPE behavior can vary substantially depending on Python version
            # and platform; using our own pipes keeps it simple, predictable, and fast.
            stdout_r, stdout_w = os.pipe()
            stderr_r, stderr_w = os.pipe()
            close_fds |= {stdout_r, stdout_w, stderr_r, stderr_w}
            kwargs = dict(stdout=stdout_w, stderr=stderr_w)
        else:
            kwargs = {}

        try:
            global process
            process = subprocess.Popen(cmdline, cwd=cwd, env=env, bufsize=0, **kwargs)
        except Exception as exc:
            raise messaging.Message.cant_handle(
                "Couldn't spawn debuggee: {0}\n\nCommand line:{1!r}", exc, cmdline
            )

        log.info("Spawned {0}.", describe())
        atexit.register(kill)
        adapter.channel.send_event(
            "process",
            {
                "startMethod": "launch",
                "isLocalProcess": True,
                "systemProcessId": process.pid,
                "name": process_name,
                "pointerSize": struct.calcsize("P") * 8,
            },
        )

        if redirect_output:
            encoding = env.get("PYTHONIOENCODING", locale.getpreferredencoding())
            for category, fd, tee in [
                ("stdout", stdout_r, sys.stdout),
                ("stderr", stderr_r, sys.stderr),
            ]:
                output.CaptureOutput(category, fd, tee.fileno(), encoding)
                close_fds.remove(fd)

        wait_thread = threading.Thread(target=wait_for_exit, name="wait_for_exit()")
        wait_thread.daemon = True
        wait_thread.start()

    finally:
        for fd in close_fds:
            try:
                os.close(fd)
            except Exception:
                log.exception()


def kill():
    if process is None:
        return
    try:
        if process.poll() is None:
            log.info("Killing {0}", describe())
            process.kill()
    except Exception:
        log.exception("Failed to kill {0}", describe())


def wait_for_exit():
    from ptvsd.launcher import adapter, output

    try:
        code = process.wait()
    except Exception:
        log.exception("Couldn't determine process exit code:")
        code = -1

    log.info("{0} exited with code {1}", describe(), code)
    output.wait_for_remaining_output()
    try:
        adapter.channel.send_event("exited", {"exitCode": code})
    except Exception:
        pass

    if any(pred(code) for pred in wait_on_exit_predicates):
        _wait_for_user_input()

    try:
        adapter.channel.send_event("terminated")
    except Exception:
        pass


def _wait_for_user_input():
    if sys.stdout and sys.stdin:
        from ptvsd.common import log

        can_getch = sys.stdin.isatty()
        if can_getch:
            try:
                import msvcrt
            except ImportError:
                can_getch = False

        if can_getch:
            log.debug("msvcrt available - waiting for user input via getch()")
            sys.stdout.write("Press any key to continue . . . ")
            sys.stdout.flush()
            msvcrt.getch()
        else:
            log.debug("msvcrt not available - waiting for user input via read()")
            sys.stdout.write("Press Enter to continue . . . ")
            sys.stdout.flush()
            sys.stdin.read(1)
