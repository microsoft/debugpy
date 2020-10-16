import os
import sys
import subprocess


def breaknow():
    print('break here')


if '--fork-in-subprocess' in sys.argv:
    if sys.platform == 'win32':
        popen = subprocess.Popen([sys.executable, __file__, '--forked'])
        pid = popen.pid
    else:
        pid = os.fork()
    print('currently in pid: %s, ppid: %s' % (os.getpid(), os.getppid()))
    print('os.fork returned', pid)
    breaknow()

elif '--forked' in sys.argv:
    print('currently in pid: %s, ppid: %s' % (os.getpid(), os.getppid()))
    breaknow()

elif '--fork-in-subprocess' not in sys.argv:
    out = subprocess.check_output([sys.executable, __file__, '--fork-in-subprocess'])
    breaknow()
    print('\n\nin pid %s, output from subprocess.run:\n%s' % (os.getpid(), out.decode('utf-8')))
    print('TEST SUCEEDED!')
