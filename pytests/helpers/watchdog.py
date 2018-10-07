# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

import multiprocessing
import os
import sys
import psutil


def create(pid):
    proc = multiprocessing.Process(target=watch, args=(os.getpid(), pid))
    proc.daemon = True
    proc.start()


def watch(test_pid, ptvsd_pid):
    test_process = psutil.Process(test_pid)
    ptvsd_process = psutil.Process(ptvsd_pid)

    test_process.wait()

    if ptvsd_process.is_running():
        print('ptvsd(pid=%d) still running after test process exited! Killing it.' % ptvsd_pid)
        procs = [ptvsd_process]
        try:
            procs += ptvsd_process.children(recursive=True)
        except:
            pass
        for p in procs:
            try:
                p.kill()
            except:
                pass


if __name__ == '__main__':
    _,  test_pid, ptvsd_pid = sys.argv
    watch(test_pid, ptvsd_pid)
