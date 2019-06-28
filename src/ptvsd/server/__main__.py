# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, with_statement

import numbers
import os.path
import runpy
import sys
import site
import sysconfig

# ptvsd can also be invoked directly rather than via -m. In this case, the
# first entry on sys.path is the one added automatically by Python for the
# directory containing this file. This means that 1) import ptvsd will not
# work, since we need the parent directory of ptvsd/ to be on path, rather
# than ptvsd/ itself, and 2) many other absolute imports will break, because
# they will be resolved relative to ptvsd/ - e.g. import socket will then
# try to import ptvsd/socket.py!
#
# To fix this, we need to replace the automatically added entry such that it
# points at the parent directory instead, import ptvsd from that directory,
# and then remove than entry altogether so that it doesn't affect any further
# imports. For example, suppose the user did:
#
#   python /foo/bar/ptvsd ...
#
# At the beginning of this script, sys.path will contain '/foo/bar/ptvsd' as
# the first entry. What we want is to replace it with '/foo/bar', then import
# ptvsd with that in effect, and then remove it before continuing execution.
if __name__ == '__main__' and 'ptvsd' not in sys.modules:
    sys.path[0] = os.path.dirname(sys.path[0])
    import ptvsd  # noqa
    del sys.path[0]

import pydevd

import threading  # Import after pydevd.

import ptvsd.server._remote
import ptvsd.server.options
import ptvsd.server.runner
from ptvsd.server.multiproc import listen_for_subprocesses

# When forming the command line involving __main__.py, it might be tempting to
# import it as a module, and then use its __file__. However, that does not work
# reliably, because __file__ can be a relative path - and when it is relative,
# that's relative to the current directory at the time import was done, which
# may be different from the current directory at the time the path is used.
#
# So, to be able to correctly locate the script at any point, we compute the
# absolute path at import time.
__file__ = os.path.abspath(__file__)

TARGET = '<filename> | -m <module> | -c <code> | --pid <pid>'

HELP = ('''ptvsd %s
See https://aka.ms/ptvsd for documentation.

Usage: ptvsd --host <address> [--port <port>] [--wait] [--multiprocess]
             [--log-dir <path>]
             ''' + TARGET + '''
''') % (ptvsd.__version__,)


# In Python 2, arguments are passed as bytestrings in locale encoding
# For uniformity, parse them into Unicode strings.
def string(s):
    if isinstance(s, bytes):
        s = s.decode(sys.getfilesystemencoding())
    return s


def in_range(parser, start, stop):

    def parse(s):
        n = parser(s)
        if start is not None and n < start:
            raise ValueError('must be >= %s' % start)
        if stop is not None and n >= stop:
            raise ValueError('must be < %s' % stop)
        return n

    return parse


port = in_range(int, 0, 2 ** 16)

pid = in_range(int, 0, None)


def print_help_and_exit(switch, it):
    print(HELP, file=sys.stderr)
    sys.exit(0)


def print_version_and_exit(switch, it):
    print(ptvsd.__version__)
    sys.exit(0)


def set_arg(varname, parser):

    def action(arg, it):
        value = parser(next(it))
        setattr(ptvsd.server.options, varname, value)

    return action


def set_true(varname):

    def do(arg, it):
        setattr(ptvsd.server.options, varname, True)

    return do


def set_log_dir():

    def do(arg, it):
        ptvsd.common.options.log_dir = string(next(it))

    return do


def set_target(kind, parser=None):

    def do(arg, it):
        ptvsd.server.options.target_kind = kind
        ptvsd.server.options.target = arg if parser is None else parser(next(it))

    return do


def set_nodebug(arg, it):
    # --nodebug implies --client
    ptvsd.server.options.no_debug = True
    ptvsd.server.options.client = True


switches = [
    # Switch                    Placeholder         Action                                  Required
    # ======                    ===========         ======                                  ========

    # Switches that are documented for use by end users.
    (('-?', '-h', '--help'), None, print_help_and_exit, False),
    (('-V', '--version'), None, print_version_and_exit, False),
    ('--host', '<address>', set_arg('host', string), True),
    ('--port', '<port>', set_arg('port', port), False),
    ('--wait', None, set_true('wait'), False),
    ('--multiprocess', None, set_true('multiprocess'), False),
    ('--log-dir', '<path>', set_log_dir(), False),

    # Switches that are used internally by the IDE or ptvsd itself.
    ('--nodebug', None, set_nodebug, False),
    ('--client', None, set_true('client'), False),
    ('--subprocess-of', '<pid>', set_arg('subprocess_of', pid), False),
    ('--subprocess-notify', '<port>', set_arg('subprocess_notify', port), False),

    # Targets. The '' entry corresponds to positional command line arguments,
    # i.e. the ones not preceded by any switch name.
    ('', '<filename>', set_target('file'), False),
    ('-m', '<module>', set_target('module', string), False),
    ('-c', '<code>', set_target('code', string), False),
    ('--pid', '<pid>', set_target('pid', pid), False),
]


def parse(args):
    unseen_switches = list(switches)

    it = iter(args)
    while True:
        try:
            arg = next(it)
        except StopIteration:
            raise ValueError('missing target: ' + TARGET)

        switch = arg if arg.startswith('-') else ''
        for i, (sw, placeholder, action, _) in enumerate(unseen_switches):
            if isinstance(sw, str):
                sw = (sw,)
            if switch in sw:
                del unseen_switches[i]
                break
        else:
            raise ValueError('unrecognized switch ' + switch)

        try:
            action(arg, it)
        except StopIteration:
            assert placeholder is not None
            raise ValueError('%s: missing %s' % (switch, placeholder))
        except Exception as ex:
            raise ValueError('invalid %s %s: %s' % (switch, placeholder, str(ex)))

        if ptvsd.server.options.target is not None:
            break

    for sw, placeholder, _, required in unseen_switches:
        if required:
            if not isinstance(sw, str):
                sw = sw[0]
            message = 'missing required %s' % sw
            if placeholder is not None:
                message += ' ' + placeholder
            raise ValueError(message)

    return it


daemon = None


def setup_connection():
    ptvsd.common.log.debug('sys.prefix: {0}', (sys.prefix,))

    if hasattr(sys, 'base_prefix'):
        ptvsd.common.log.debug('sys.base_prefix: {0}', sys.base_prefix)

    if hasattr(sys, 'real_prefix'):
        ptvsd.common.log.debug('sys.real_prefix: {0}', sys.real_prefix)

    if hasattr(site, 'getusersitepackages'):
        ptvsd.common.log.debug('site.getusersitepackages(): {0}', site.getusersitepackages())

    if hasattr(site, 'getsitepackages'):
        ptvsd.common.log.debug('site.getsitepackages(): {0}', site.getsitepackages())

    for path in sys.path:
        if os.path.exists(path) and os.path.basename(path) == 'site-packages':
            ptvsd.common.log.debug('Folder with "site-packages" in sys.path: {0}', path)

    for path_name in {'stdlib', 'platstdlib', 'purelib', 'platlib'} & set(
            sysconfig.get_path_names()):
        ptvsd.common.log.debug('sysconfig {0}: {1}', path_name, sysconfig.get_path(path_name))

    ptvsd.common.log.debug('os dir: {0}', os.path.dirname(os.__file__))
    ptvsd.common.log.debug('threading dir: {0}', os.path.dirname(threading.__file__))

    opts = ptvsd.server.options
    pydevd.apply_debugger_options({
        'server': not opts.client,
        'client': opts.host,
        'port': opts.port,
        'multiprocess': opts.multiprocess,
    })

    if opts.multiprocess:
        listen_for_subprocesses()

    # We need to set up sys.argv[0] before invoking attach() or enable_attach(),
    # because they use it to report the 'process' event. Thus, we can't rely on
    # run_path() and run_module() doing that, even though they will eventually.

    if opts.target_kind == 'code':
        sys.argv[0] = '-c'
    elif opts.target_kind == 'file':
        sys.argv[0] = opts.target
    elif opts.target_kind == 'module':
        # Add current directory to path, like Python itself does for -m. This must
        # be in place before trying to use find_spec below to resolve submodules.
        sys.path.insert(0, '')

        # We want to do the same thing that run_module() would do here, without
        # actually invoking it. On Python 3, it's exposed as a public API, but
        # on Python 2, we have to invoke a private function in runpy for this.
        # Either way, if it fails to resolve for any reason, just leave argv as is.
        try:
            if sys.version_info >= (3,):
                from importlib.util import find_spec
                spec = find_spec(opts.target)
                if spec is not None:
                    sys.argv[0] = spec.origin
            else:
                _, _, _, sys.argv[0] = runpy._get_module_details(opts.target)
        except Exception:
            ptvsd.common.log.exception('Error determining module path for sys.argv')
    else:
        assert False

    ptvsd.common.log.debug('sys.argv after patching: {0!r}', sys.argv)

    addr = (opts.host, opts.port)

    global daemon
    if opts.no_debug:
        daemon = ptvsd.server.runner.Daemon()
        if not daemon.wait_for_launch(addr):
            return
    elif opts.client:
        daemon = ptvsd.server._remote.attach(addr)
    else:
        daemon = ptvsd.server._remote.enable_attach(addr)

    if opts.wait:
        ptvsd.wait_for_attach()


def run_file():
    setup_connection()

    target = ptvsd.server.options.target
    ptvsd.common.log.info('Running file {0}', target)

    # run_path has one difference with invoking Python from command-line:
    # if the target is a file (rather than a directory), it does not add its
    # parent directory to sys.path. Thus, importing other modules from the
    # same directory is broken unless sys.path is patched here.
    if os.path.isfile(target):
        dir = os.path.dirname(target)
        ptvsd.common.log.debug('Adding {0} to sys.path.', dir)
        sys.path.insert(0, dir)
    else:
        ptvsd.common.log.debug('Not a file: {0}', target)

    runpy.run_path(target, run_name='__main__')


def run_module():
    setup_connection()

    # On Python 2, module name must be a non-Unicode string, because it ends up
    # a part of module's __package__, and Python will refuse to run the module
    # if __package__ is Unicode.
    target = ptvsd.server.options.target
    if sys.version_info < (3,) and not isinstance(target, bytes):
        target = target.encode(sys.getfilesystemencoding())

    ptvsd.common.log.info('Running module {0}', target)

    # Docs say that runpy.run_module is equivalent to -m, but it's not actually
    # the case for packages - -m sets __name__ to '__main__', but run_module sets
    # it to `pkg.__main__`. This breaks everything that uses the standard pattern
    # __name__ == '__main__' to detect being run as a CLI app. On the other hand,
    # runpy._run_module_as_main is a private function that actually implements -m.
    try:
        run_module_as_main = runpy._run_module_as_main
    except AttributeError:
        ptvsd.common.log.warning('runpy._run_module_as_main is missing, falling back to run_module.')
        runpy.run_module(target, alter_sys=True)
    else:
        run_module_as_main(target, alter_argv=True)


def run_code():
    ptvsd.common.log.info('Running code:\n\n{0}', ptvsd.server.options.target)

    # Add current directory to path, like Python itself does for -c.
    sys.path.insert(0, '')
    code = compile(ptvsd.server.options.target, '<string>', 'exec')
    setup_connection()
    eval(code, {})


def attach_to_pid():

    def quoted_str(s):
        if s is None:
            return s
        assert not isinstance(s, bytes)
        unescaped = set(chr(ch) for ch in range(32, 127)) - {'"', "'", '\\'}

        def escape(ch):
            return ch if ch in unescaped else '\\u%04X' % ord(ch)

        return 'u"' + ''.join(map(escape, s)) + '"'

    ptvsd.common.log.info('Attaching to process with ID {0}', ptvsd.server.options.target)

    pid = ptvsd.server.options.target
    host = quoted_str(ptvsd.server.options.host)
    port = ptvsd.server.options.port
    client = ptvsd.server.options.client
    log_dir = quoted_str(ptvsd.common.options.log_dir)

    ptvsd_path = os.path.abspath(os.path.join(ptvsd.server.__file__, '../..'))
    if isinstance(ptvsd_path, bytes):
        ptvsd_path = ptvsd_path.decode(sys.getfilesystemencoding())
    ptvsd_path = quoted_str(ptvsd_path)

    # pydevd requires injected code to not contain any single quotes.
    code = '''
import os
assert os.getpid() == {pid}

import sys
sys.path.insert(0, {ptvsd_path})
import ptvsd
del sys.path[0]

import ptvsd.server.options
ptvsd.common.options.log_dir = {log_dir}
ptvsd.server.options.client = {client}
ptvsd.server.options.host = {host}
ptvsd.server.options.port = {port}

import ptvsd.common.log
ptvsd.common.log.to_file()
ptvsd.common.log.info("Debugger successfully injected")

if ptvsd.server.options.client:
    from ptvsd.server._remote import attach
    attach(({host}, {port}))
else:
    ptvsd.server.enable_attach()
'''.format(**locals())

    ptvsd.common.log.debug('Injecting debugger into target process: \n"""{0}\n"""'.format(code))
    assert "'" not in code, 'Injected code should not contain any single quotes'

    pydevd_attach_to_process_path = os.path.join(
        os.path.dirname(pydevd.__file__),
        'pydevd_attach_to_process')
    sys.path.insert(0, pydevd_attach_to_process_path)
    from add_code_to_python_process import run_python_code
    run_python_code(pid, code, connect_debugger_tracing=True)


def main(argv=sys.argv):
    saved_argv = list(argv)
    try:
        sys.argv[:] = [argv[0]] + list(parse(argv[1:]))
    except Exception as ex:
        print(HELP + '\nError: ' + str(ex), file=sys.stderr)
        sys.exit(2)

    ptvsd.common.log.to_file()
    ptvsd.common.log.info('main({0!r})', saved_argv)
    ptvsd.common.log.info('sys.argv after parsing: {0!r}', sys.argv)

    try:
        run = {
            'file': run_file,
            'module': run_module,
            'code': run_code,
            'pid': attach_to_pid,
        }[ptvsd.server.options.target_kind]
        run()
    except SystemExit as ex:
        ptvsd.common.log.exception('Debuggee exited via SystemExit', level='debug')
        if daemon is not None:
            if ex.code is None:
                daemon.exitcode = 0
            elif isinstance(ex.code, numbers.Integral):
                daemon.exitcode = int(ex.code)
            else:
                daemon.exitcode = 1
        raise


if __name__ == '__main__':
    main()
