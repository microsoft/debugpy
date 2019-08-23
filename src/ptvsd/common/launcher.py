# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

__all__ = ["main"]

import os
import os.path
import socket
import subprocess
import sys

# Force absolute path on Python 2.
__file__ = os.path.abspath(__file__)


WAIT_ON_NORMAL_SWITCH = "--wait-on-normal"
WAIT_ON_ABNORMAL_SWITCH = "--wait-on-abnormal"
INTERNAL_PORT_SWITCH = "--internal-port"


_wait_on_normal_exit = False
_wait_on_abnormal_exit = False
_internal_pid_server_port = None


HELP = """Usage: launcher [{normal}] [{abnormal}] <args>
python launcher.py {normal} {abnormal} -- <python args go here>
""".format(
    normal=WAIT_ON_NORMAL_SWITCH, abnormal=WAIT_ON_ABNORMAL_SWITCH
)


def main(argv=sys.argv):
    try:
        process_args = [sys.executable] + list(parse(argv[1:]))
    except Exception as ex:
        print(HELP + "\nError: " + str(ex), file=sys.stderr)
        sys.exit(2)

    p = subprocess.Popen(args=process_args)
    _send_pid(p.pid)
    exit_code = p.wait()

    if _wait_on_normal_exit and exit_code == 0:
        _wait_for_user()
    elif _wait_on_abnormal_exit and exit_code != 0:
        _wait_for_user()

    sys.exit(exit_code)


def _wait_for_user():
    if sys.__stdout__ and sys.__stdin__:
        try:
            import msvcrt
        except ImportError:
            sys.__stdout__.write("Press Enter to continue . . . ")
            sys.__stdout__.flush()
            sys.__stdin__.read(1)
        else:
            sys.__stdout__.write("Press any key to continue . . . ")
            sys.__stdout__.flush()
            msvcrt.getch()


def parse_arg(arg, it):
    if arg == WAIT_ON_NORMAL_SWITCH:
        global _wait_on_normal_exit
        _wait_on_normal_exit = True
    elif arg == WAIT_ON_ABNORMAL_SWITCH:
        global _wait_on_abnormal_exit
        _wait_on_abnormal_exit = True
    elif arg == INTERNAL_PORT_SWITCH:
        global _internal_pid_server_port
        _internal_pid_server_port = int(next(it))
    else:
        raise AssertionError("Invalid argument passed to launcher.")


def parse(argv):
    it = iter(argv)
    arg = next(it)
    while arg != "--":
        parse_arg(arg, it)
        arg = next(it)
    return it


def _send_pid(pid):
    assert _internal_pid_server_port is not None
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect(("127.0.0.1", _internal_pid_server_port))
        sock.sendall(b"%d" % pid)
    finally:
        sock.close()


if __name__ == "__main__":
    main()
