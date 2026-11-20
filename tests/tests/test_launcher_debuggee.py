# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import os
import subprocess
import sys
import textwrap
import time

import pytest

DRIVER = textwrap.dedent("""
    import os
    import sys
    import time

    from debugpy import launcher
    from debugpy.launcher import debuggee


    class Channel:
        def __init__(self):
            self.events = []

        def send_event(self, name, body=None):
            self.events.append(name)


    launcher.channel = Channel()
    debuggee.spawn(
        "debuggee", [sys.executable, "-c", "pass"], dict(os.environ), False
    )

    deadline = time.time() + 60
    while "terminated" not in launcher.channel.events:
        if time.time() > deadline:
            print("Timed out waiting for the debuggee to exit.", flush=True)
            sys.exit(2)
        time.sleep(0.05)

    foreground = os.tcgetpgrp(0)
    print(
        "Foreground process group is {0}, launcher process group is {1}.".format(
            foreground, os.getpgrp()
        ),
        flush=True,
    )
    sys.exit(0 if foreground == os.getpgrp() else 1)
    """)


@pytest.mark.skipif(
    sys.platform == "win32", reason="POSIX foreground process groups only"
)
def test_launcher_restores_foreground_process_group(tmp_path):
    import fcntl
    import pty
    import select
    import termios

    driver = tmp_path / "driver.py"
    driver.write_text(DRIVER)

    src = os.path.join(os.path.dirname(__file__), "..", "..", "src")
    env = dict(os.environ)
    env["PYTHONPATH"] = os.path.abspath(src) + os.pathsep + env.get("PYTHONPATH", "")

    master, slave = pty.openpty()

    def preexec_fn():
        os.setsid()
        fcntl.ioctl(0, termios.TIOCSCTTY, 0)

    proc = subprocess.Popen(
        [sys.executable, str(driver)],
        stdin=slave,
        stdout=slave,
        stderr=slave,
        preexec_fn=preexec_fn,
        env=env,
        close_fds=True,
    )
    os.close(slave)

    output = b""
    timed_out = False
    try:
        deadline = time.time() + 90
        while proc.poll() is None:
            if time.time() > deadline:
                timed_out = True
                break
            ready, _, _ = select.select([master], [], [], 0.1)
            if master in ready:
                try:
                    chunk = os.read(master, 65536)
                except OSError:
                    break
                if not chunk:
                    break
                output += chunk
    finally:
        os.close(master)
        if proc.poll() is None:
            proc.kill()

    proc.wait(timeout=10)
    assert (
        not timed_out
    ), "Driver did not exit in time; output so far:\n" + output.decode(errors="replace")
    assert proc.returncode == 0, output.decode(errors="replace")
