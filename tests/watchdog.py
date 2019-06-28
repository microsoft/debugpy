# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import multiprocessing
import os
import sys
import platform
import psutil
import tempfile


def create(pid):
    proc = multiprocessing.Process(target=watch, args=(os.getpid(), pid))
    proc.daemon = True
    proc.start()


def watch(test_pid, ptvsd_pid):
    test_process = psutil.Process(test_pid)
    try:
        ptvsd_process = psutil.Process(ptvsd_pid)
    except psutil.NoSuchProcess:
        # ptvsd process has already exited, so there's nothing to watch.
        return

    test_process.wait()

    if ptvsd_process.is_running():
        print('ptvsd(pid=%d) still running after test process exited! Killing it.' % ptvsd_pid)
        procs = [ptvsd_process]
        try:
            procs += ptvsd_process.children(recursive=True)
        except:
            pass
        for p in procs:
            if platform.system() == 'Linux':
                print('Generating core dump for ptvsd(pid=%d) ...' % p.pid)
                try:
                    # gcore will automatically add pid to the filename
                    core_file = os.path.join(tempfile.gettempdir(), 'ptvsd_core')
                    os.system('gcore -o %s %d' % (core_file, p.pid))
                except:
                    pass
            try:
                p.kill()
            except:
                pass


if __name__ == '__main__':
    _,  test_pid, ptvsd_pid = sys.argv
    watch(test_pid, ptvsd_pid)
