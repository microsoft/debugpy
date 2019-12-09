# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, division, print_function, unicode_literals

import os
import runpy
import sys

# ptvsd.__main__ should have preloaded pydevd properly before importing this module.
# Otherwise, some stdlib modules above might have had imported threading before pydevd
# could perform the necessary detours in it.
assert "pydevd" in sys.modules
import pydevd

import ptvsd
from ptvsd.common import compat, fmt, log
from ptvsd.server import options


TARGET = "<filename> | -m <module> | -c <code> | --pid <pid>"

HELP = """ptvsd {0}
See https://aka.ms/ptvsd for documentation.

Usage: ptvsd [--client] --host <address> [--port <port>]
             [--wait]
             [--no-subprocesses]
             [--log-dir <path>] [--log-stderr]
             {1}
""".format(
    ptvsd.__version__, TARGET
)


def in_range(parser, start, stop):
    def parse(s):
        n = parser(s)
        if start is not None and n < start:
            raise ValueError(fmt("must be >= {0}", start))
        if stop is not None and n >= stop:
            raise ValueError(fmt("must be < {0}", stop))
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


def set_arg(varname, parser=(lambda x: x), target=options):
    def do(arg, it):
        value = parser(next(it))
        setattr(target, varname, value)

    return do


def set_const(varname, value, target=options):
    def do(arg, it):
        setattr(target, varname, value)

    return do


def set_log_stderr():
    def do(arg, it):
        log.stderr.levels |= set(log.LEVELS)

    return do


def set_target(kind, parser=(lambda x: x), positional=False):
    def do(arg, it):
        options.target_kind = kind
        options.target = parser(arg if positional else next(it))

    return do


# fmt: off
switches = [
    # Switch                    Placeholder         Action                                  Required
    # ======                    ===========         ======                                  ========

    # Switches that are documented for use by end users.
    (("-?", "-h", "--help"),    None,               print_help_and_exit,                    False),
    (("-V", "--version"),       None,               print_version_and_exit,                 False),
    ("--client",                None,               set_const("client", True),              False),
    ("--host",                  "<address>",        set_arg("host"),                        True),
    ("--port",                  "<port>",           set_arg("port", port),                  False),
    ("--wait",                  None,               set_const("wait", True),                False),
    ("--no-subprocesses",       None,               set_const("multiprocess", False),       False),
    ("--log-dir",               "<path>",           set_arg("log_dir", target=log),         False),
    ("--log-stderr",            None,               set_log_stderr(),                       False),

    # Switches that are used internally by the IDE or ptvsd itself.
    ("--client-access-token",   "<token>",          set_arg("client_access_token"),         False),

    # Targets. The "" entry corresponds to positional command line arguments,
    # i.e. the ones not preceded by any switch name.
    ("",                        "<filename>",       set_target("file", positional=True),    False),
    ("-m",                      "<module>",         set_target("module"),                   False),
    ("-c",                      "<code>",           set_target("code"),                     False),
    ("--pid",                   "<pid>",            set_target("pid", pid),                 False),
]
# fmt: on


def parse(args, options=options):
    seen = set()
    it = (compat.filename(arg) for arg in args)

    while True:
        try:
            arg = next(it)
        except StopIteration:
            raise ValueError("missing target: " + TARGET)

        switch = arg if arg.startswith("-") else ""
        for i, (sw, placeholder, action, _) in enumerate(switches):
            if not isinstance(sw, tuple):
                sw = (sw,)
            if switch in sw:
                break
        else:
            raise ValueError("unrecognized switch " + switch)

        if i in seen:
            raise ValueError("duplicate switch " + switch)
        else:
            seen.add(i)

        try:
            action(arg, it)
        except StopIteration:
            assert placeholder is not None
            raise ValueError(fmt("{0}: missing {1}", switch, placeholder))
        except Exception as exc:
            raise ValueError(fmt("invalid {0} {1}: {2}", switch, placeholder, exc))

        if options.target is not None:
            break

    for i, (sw, placeholder, _, required) in enumerate(switches):
        if not required or i in seen:
            continue
        if isinstance(sw, tuple):
            sw = sw[0]
        message = fmt("missing required {0}", sw)
        if placeholder is not None:
            message += " " + placeholder
        raise ValueError(message)

    if options.target_kind == "pid" and options.wait:
        raise ValueError("--pid does not support --wait")

    return it


def setup_debug_server(argv_0):
    # We need to set up sys.argv[0] before invoking attach() or enable_attach(),
    # because they use it to report the "process" event. Thus, we can't rely on
    # run_path() and run_module() doing that, even though they will eventually.
    sys.argv[0] = compat.filename(argv_0)
    log.debug("sys.argv after patching: {0!r}", sys.argv)

    debug = ptvsd.attach if options.client else ptvsd.enable_attach
    debug(address=options, multiprocess=options)

    if options.wait:
        ptvsd.wait_for_attach()


def run_file():
    setup_debug_server(options.target)

    # run_path has one difference with invoking Python from command-line:
    # if the target is a file (rather than a directory), it does not add its
    # parent directory to sys.path. Thus, importing other modules from the
    # same directory is broken unless sys.path is patched here.
    if os.path.isfile(options.target):
        dir = os.path.dirname(options.target)
        sys.path.insert(0, dir)
    else:
        log.debug("Not a file: {0!j}", options.target)

    log.describe_environment("Pre-launch environment:")
    log.info("Running file {0!j}", options.target)
    runpy.run_path(options.target, run_name="__main__")


def run_module():
    # Add current directory to path, like Python itself does for -m. This must
    # be in place before trying to use find_spec below to resolve submodules.
    sys.path.insert(0, "")

    # We want to do the same thing that run_module() would do here, without
    # actually invoking it. On Python 3, it's exposed as a public API, but
    # on Python 2, we have to invoke a private function in runpy for this.
    # Either way, if it fails to resolve for any reason, just leave argv as is.
    argv_0 = sys.argv[0]
    try:
        if sys.version_info >= (3,):
            from importlib.util import find_spec

            spec = find_spec(options.target)
            if spec is not None:
                argv_0 = spec.origin
        else:
            _, _, _, argv_0 = runpy._get_module_details(options.target)
    except Exception:
        log.exception("Error determining module path for sys.argv")

    setup_debug_server(argv_0)

    # On Python 2, module name must be a non-Unicode string, because it ends up
    # a part of module's __package__, and Python will refuse to run the module
    # if __package__ is Unicode.
    target = (
        compat.filename_bytes(options.target)
        if sys.version_info < (3,)
        else options.target
    )

    log.describe_environment("Pre-launch environment:")
    log.info("Running module {0!r}", target)

    # Docs say that runpy.run_module is equivalent to -m, but it's not actually
    # the case for packages - -m sets __name__ to "__main__", but run_module sets
    # it to "pkg.__main__". This breaks everything that uses the standard pattern
    # __name__ == "__main__" to detect being run as a CLI app. On the other hand,
    # runpy._run_module_as_main is a private function that actually implements -m.
    try:
        run_module_as_main = runpy._run_module_as_main
    except AttributeError:
        log.warning("runpy._run_module_as_main is missing, falling back to run_module.")
        runpy.run_module(target, alter_sys=True)
    else:
        run_module_as_main(target, alter_argv=True)


def run_code():
    log.describe_environment("Pre-launch environment:")
    log.info("Running code:\n\n{0}", options.target)

    # Add current directory to path, like Python itself does for -c.
    sys.path.insert(0, "")
    code = compile(options.target, "<string>", "exec")

    setup_debug_server("-c")
    eval(code, {})


def attach_to_pid():
    log.info("Attaching to process with PID={0}", options.target)

    pid = options.target

    attach_pid_injected_dirname = os.path.join(
        os.path.dirname(ptvsd.__file__), "server"
    )
    assert os.path.exists(attach_pid_injected_dirname)

    log_dir = (log.log_dir or "").replace("\\", "/")
    encode = lambda s: list(bytearray(s.encode("utf-8")))
    setup = {
        "script": encode(attach_pid_injected_dirname),
        "host": encode(options.host),
        "port": options.port,
        "client": options.client,
        "log_dir": encode(log_dir),
        "client_access_token": encode(options.client_access_token),
    }

    python_code = """
import sys;
import codecs;
decode = lambda s: codecs.utf_8_decode(bytearray(s))[0];
script_path = decode({script});
sys.path.insert(0, script_path);
import attach_pid_injected;
sys.path.remove(script_path);
host = decode({host});
log_dir = decode({log_dir}) or None;
client_access_token = decode({client_access_token}) or None;
attach_pid_injected.attach(
    port={port},
    host=host,
    client={client},
    log_dir=log_dir,
    client_access_token=client_access_token,
)
"""
    python_code = python_code.replace("\r", "").replace("\n", "").format(**setup)
    log.info("Code to be injected: \n{0}", python_code.replace(";", ";\n"))

    # pydevd restriction on characters in injected code.
    assert not (
        {'"', "'", "\r", "\n"} & set(python_code)
    ), "Injected code should not contain any single quotes, double quotes, or newlines."

    pydevd_attach_to_process_path = os.path.join(
        os.path.dirname(pydevd.__file__), "pydevd_attach_to_process"
    )

    assert os.path.exists(pydevd_attach_to_process_path)
    sys.path.append(pydevd_attach_to_process_path)

    try:
        import add_code_to_python_process  # noqa

        log.info("Injecting code into process with PID={0} ...", pid)
        add_code_to_python_process.run_python_code(
            pid,
            python_code,
            connect_debugger_tracing=True,
            show_debug_info=int(os.getenv("PTVSD_ATTACH_BY_PID_DEBUG_INFO", "0")),
        )
    except Exception:
        raise log.exception("Code injection into PID={0} failed:", pid)
    log.info("Code injection into PID={0} completed.", pid)


def main():
    original_argv = list(sys.argv)
    try:
        sys.argv[1:] = parse(sys.argv[1:])
    except Exception as ex:
        print(HELP + "\nError: " + str(ex), file=sys.stderr)
        sys.exit(2)

    log.to_file(prefix="ptvsd.server")
    log.describe_environment("ptvsd.server startup environment:")
    log.info(
        "sys.argv before parsing: {0!r}\n" "         after parsing:  {1!r}",
        original_argv,
        sys.argv,
    )

    try:
        run = {
            "file": run_file,
            "module": run_module,
            "code": run_code,
            "pid": attach_to_pid,
        }[options.target_kind]
        run()
    except SystemExit as ex:
        log.exception("Debuggee exited via SystemExit: {0!r}", ex.code, level="debug")
        raise
