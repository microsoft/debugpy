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
    try:
        ppid = os.getppid()
    except:
        ppid = '<unknown>'
    print('currently in pid: %s, ppid: %s' % (os.getpid(), ppid))
    print('os.fork returned', pid)
    breaknow()

elif '--forked' in sys.argv:
    try:
        ppid = os.getppid()
    except:
        ppid = '<unknown>'
    print('currently in pid: %s, ppid: %s' % (os.getpid(), ppid))
    breaknow()

elif '--fork-in-subprocess' not in sys.argv:
    out = subprocess.check_output([sys.executable, __file__, '--fork-in-subprocess'])
    breaknow()
    print('\n\nin pid %s, output from subprocess.run:\n%s' % (os.getpid(), out.decode('utf-8')))
    print('TEST SUCEEDED!')
