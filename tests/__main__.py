import os
import os.path
import sys
import unittest


TEST_ROOT = os.path.dirname(__file__)
PROJECT_ROOT = os.path.dirname(TEST_ROOT)


def convert_argv(argv):
    help  = False
    quick = False
    args = []
    modules = set()
    for arg in argv:
        if arg == '--quick':
            quick = True
            continue
        elif arg == '--full':
            quick = False
            continue

        # Unittest's main has only flags and positional args.
        # So we don't worry about options with values.
        if not arg.startswith('-'):
            # It must be the name of a test, case, module, or file.
            # We convert filenames to module names.  For filenames
            # we support specifying a test name by appending it to
            # the filename with a ":" in between.
            mod, _, test = arg.partition(':')
            if mod.endswith(os.sep):
                mod = mod.rsplit(os.sep, 1)[0]
            mod = mod.rsplit('.py', 1)[0]
            mod = mod.replace(os.sep, '.')
            arg = mod if not test else mod + '.' + test
            modules.add(mod)
        elif arg in ('-h', '--help'):
            help = True
        args.append(arg)

    # We make the "executable" a single arg because unittest.main()
    # doesn't work if we split it into 3 parts.
    cmd = [sys.executable + ' -m unittest']
    if not modules and not help:
        # Do discovery.
        if quick:
            start = os.path.join(TEST_ROOT, 'ptvsd')
        elif sys.version_info[0] != 3:
            start = os.path.join(TEST_ROOT, 'ptvsd')
        else:
            start = PROJECT_ROOT
        cmd += [
            'discover',
            '--top-level-directory', PROJECT_ROOT,
            '--start-directory', start,
        ]
    return cmd + args


def fix_sys_path():
    pydevdroot = os.path.join(PROJECT_ROOT, 'ptvsd', 'pydevd')
    if not sys.path[0] or sys.path[0] == '.':
        sys.path.insert(1, pydevdroot)
    else:
        sys.path.insert(0, pydevdroot)


if __name__ == '__main__':
    argv = convert_argv(sys.argv[1:])
    fix_sys_path()
    unittest.main(module=None, argv=argv)
