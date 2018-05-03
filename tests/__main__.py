from __future__ import absolute_import

import os
import os.path
import subprocess
import sys
import unittest

from . import TEST_ROOT, PROJECT_ROOT, VENDORED_ROOTS


def convert_argv(argv):
    help  = False
    quick = False
    quickpy2 = False
    network = True
    runtests = True
    lint = False
    args = []
    modules = set()
    for arg in argv:
        if arg == '--quick':
            quick = True
            continue
        if arg == '--quick-py2':
            quickpy2 = True
            continue
        elif arg == '--full':
            quick = False
            continue
        elif arg == '--network':
            network = True
            continue
        elif arg == '--no-network':
            network = False
            continue
        elif arg == '--coverage':
            runtests = 'coverage'
            continue
        elif arg == '--lint':
            lint = True
            continue
        elif arg == '--lint-only':
            lint = True
            runtests = False
            break

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

    if runtests:
        env = {}
        if network:
            env['HAS_NETWORK'] = '1'
        # We make the "executable" a single arg because unittest.main()
        # doesn't work if we split it into 3 parts.
        cmd = [sys.executable + ' -m unittest']
        if not modules and not help:
            # Do discovery.
            quickroot = os.path.join(TEST_ROOT, 'ptvsd')
            if quick:
                start = quickroot
            elif quickpy2 and sys.version_info[0] == 2:
                start = quickroot
            else:
                start = PROJECT_ROOT
            cmd += [
                'discover',
                '--top-level-directory', PROJECT_ROOT,
                '--start-directory', start,
            ]
        args = cmd + args
    else:
        args = env = None
    return args, env, runtests, lint


def fix_sys_path():
    pos = 1 if (not sys.path[0] or sys.path[0] == '.') else 0
    for projectroot in VENDORED_ROOTS:
        sys.path.insert(pos, projectroot)


def check_lint():
    print('linting...')
    args = [
        sys.executable,
        '-m', 'flake8',
        '--ignore', 'E24,E121,E123,E125,E126,E221,E226,E266,E704,E265',
        '--exclude', ','.join(VENDORED_ROOTS),
        PROJECT_ROOT,
    ]
    rc = subprocess.call(args)
    if rc != 0:
        print('...linting failed!')
        sys.exit(rc)
    print('...done')


def run_tests(argv, env, coverage=False):
    print('running tests...')
    if coverage:
        omissions = [os.path.join(root, '*') for root in VENDORED_ROOTS]
        # TODO: Drop the explicit pydevd omit once we move the subtree.
        omissions.append(os.path.join('ptvsd', 'pydevd', '*'))
        ver = 3 if sys.version_info < (3,) else 2
        omissions.append(os.path.join('ptvsd', 'reraise{}.py'.format(ver)))
        args = [
            sys.executable,
            '-m', 'coverage',
            'run',
            # We use --source instead of "--include ptvsd/*".
            '--source', 'ptvsd',
            '--omit', ','.join(omissions),
            '-m', 'unittest',
        ] + argv[1:]
        assert 'PYTHONPATH' not in env
        env['PYTHONPATH'] = os.pathsep.join(VENDORED_ROOTS)
        rc = subprocess.call(args, env=env)
        if rc != 0:
            print('...coverage failed!')
            sys.exit(rc)
        print('...done')
    else:
        os.environ.update(env)
        unittest.main(module=None, argv=argv)


if __name__ == '__main__':
    argv, env, runtests, lint = convert_argv(sys.argv[1:])
    fix_sys_path()
    if lint:
        check_lint()
    if runtests:
        if '--start-directory' in argv:
            start = argv[argv.index('--start-directory') + 1]
            print('(will look for tests under {})'.format(start))
        run_tests(
            argv,
            env,
            coverage=(runtests == 'coverage'),
        )
