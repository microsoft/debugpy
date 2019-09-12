import time
import subprocess
import sys
import os

if __name__ == '__main__':
    if 'launch-subprocesses' in sys.argv:
        n = int(sys.argv[-1])
        if n != 0:
            subprocess.Popen([sys.executable, __file__, 'launch-subprocesses', str(n - 1)])
        print('%screated %s (child of %s)' % ('\t' * (4 - n), os.getpid(), os.getppid()))

    elif 'check-subprocesses' in sys.argv:
        # Recursively create a process tree such as:
        # - parent (this process)
        #    - p3
        #      - p2
        #        - p1
        #          - p0
        #    - p3
        #      - p2
        #        - p1
        #          - p0
        subprocess.Popen([sys.executable, __file__, 'launch-subprocesses', '3'])
        subprocess.Popen([sys.executable, __file__, 'launch-subprocesses', '3'])

        print('created', os.getpid())

    while True:
        time.sleep(.1)
