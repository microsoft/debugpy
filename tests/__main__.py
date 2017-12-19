
import os
import os.path
from unittest.main import main
import sys


TEST_ROOT = os.path.dirname(__file__)
PROJECT_ROOT = os.path.dirname(TEST_ROOT)

executable = 'python3 -m unittest'

if all(arg.startswith('-') for arg in sys.argv[1:]):
    argv = [executable,
            'discover',
            '--start-directory', PROJECT_ROOT,
            '--top-level-directory', PROJECT_ROOT,
            ] + sys.argv[1:]
else:
    argv = [executable] + sys.argv[1:]
    for i, arg in enumerate(argv[1:], 1):
        if arg.startswith('-'):
            continue
        mod, _, test = arg.partition(':')
        mod = mod.rstrip(os.sep)
        mod = mod.rstrip('.py')
        mod = mod.replace(os.sep, '.')
        argv[i] = mod if not test else mod + '.' + test

main(module=None, argv=argv)
