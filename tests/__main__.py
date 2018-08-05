from __future__ import absolute_import

import argparse
import os
import os.path
import subprocess
import sys
import unittest

from . import TEST_ROOT, PROJECT_ROOT, VENDORED_ROOTS


def parse_cmdline(argv=None):
    """Obtain command line arguments and setup the test run accordingly."""

    parser = argparse.ArgumentParser(
        description="Run tests associated to the PTVSD project.",
        prog="tests",
        usage="python -m %(prog)s OPTS",
        add_help=False
    )

    # allow_abbrev was added in 3.5
    if sys.version_info >= (3, 5):
        parser.allow_abbrev = False

    parser.add_argument(
        "-c",
        "--coverage",
        help="Generate code coverage report.",
        action="store_true"
    )
    parser.add_argument(
        "--full",
        help="Do full suite of tests (disables prior --quick options).",
        action="store_false",
        dest="quick"
    )
    parser.add_argument(
        "-j",
        "--junit-xml",
        help="Output report is generated to JUnit-style XML file specified.",
        type=str
    )
    parser.add_argument(
        "-l",
        "--lint",
        help="Run and report on Linter compliance.",
        action="store_true"
    )
    parser.add_argument(
        "-L",
        "--lint-only",
        help="Run and report on Linter compliance only, do not perform tests.",
        action="store_true"
    )
    parser.add_argument(
        "-n",
        "--network",
        help="Perform tests taht require network connectivity.",
        action="store_true",
        dest="network"
    )
    parser.add_argument(
        "--no-network",
        help="Do not perform tests that require network connectivity.",
        action="store_false",
        dest="network"
    )
    parser.add_argument(
        "-q",
        "--quick",
        help="Only do the tests under test/ptvsd.",
        action="store_true",
        dest="quick"
    )
    parser.add_argument(
        "--quick-py2",
        help=("Only do the tests under test/ptvsd, that are compatible "
              "with Python 2.x."),
        action="store_true"
    )
    # these destinations have 2 switches, be explicit about the default
    parser.set_defaults(quick=False)
    parser.set_defaults(network=True)
    config, passthrough_args = parser.parse_known_args(argv)

    return config, passthrough_args


def convert_argv(argv=None):
    """Convert commandling args into unittest/linter/coverage input."""

    config, passthru = parse_cmdline(argv)

    modules = set()
    args = []
    help = False

    for arg in passthru:
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

    env = {}
    if config.network:
        env['HAS_NETWORK'] = '1'
    # We make the "executable" a single arg because unittest.main()
    # doesn't work if we split it into 3 parts.
    cmd = [sys.executable + ' -m unittest']
    if not modules and not help:
        # Do discovery.
        quickroot = os.path.join(TEST_ROOT, 'ptvsd')
        if config.quick:
            start = quickroot
        elif config.quick_py2 and sys.version_info[0] == 2:
            start = quickroot
        else:
            start = PROJECT_ROOT

        cmd += [
            'discover',
            '--top-level-directory', PROJECT_ROOT,
            '--start-directory', start,
        ]
    args = cmd + args

    return config, args, env


def is_cwd(path):
    p1 = os.path.normcase(os.path.abspath(path))
    p2 = os.path.normcase(os.getcwd())
    return p1 == p2


def fix_sys_path():
    pos = 1 if (not sys.path[0] or sys.path[0] == '.' or
                is_cwd(sys.path[0])) else 0
    for projectroot in VENDORED_ROOTS:
        sys.path.insert(pos, projectroot)


def check_lint():
    print('linting...')
    args = [
        sys.executable,
        '-m', 'flake8',
        '--config', '.flake8',
        PROJECT_ROOT,
    ]
    rc = subprocess.call(args)
    if rc != 0:
        print('...linting failed!')
        sys.exit(rc)
    print('...done')


def run_tests(argv, env, coverage, junit_xml):
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
    elif junit_xml:
        from xmlrunner import XMLTestRunner  # noqa
        os.environ.update(env)
        verbosity = 1
        if '-v' in argv or '--verbose' in argv:
            verbosity = 2
        with open(junit_xml, 'wb') as output:
            unittest.main(
                testRunner=XMLTestRunner(output=output, verbosity=verbosity),
                module=None,
                argv=argv,
            )
    else:
        os.environ.update(env)
        unittest.main(module=None, argv=argv)


if __name__ == '__main__':
    config, argv, env = convert_argv()
    fix_sys_path()

    if config.lint or config.lint_only:
        check_lint()

    if not config.lint_only:
        if '--start-directory' in argv:
            start = argv[argv.index('--start-directory') + 1]
            print('(will look for tests under {})'.format(start))

        run_tests(
            argv,
            env,
            config.coverage,
            config.junit_xml
        )
