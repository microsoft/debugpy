# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, division, print_function, unicode_literals

import functools
import os
import sys

import debugpy
from debugpy.common import compat, json
from debugpy.common.compat import unicode
from debugpy.launcher import debuggee


def launch_request(request):
    debug_options = set(request("debugOptions", json.array(unicode)))

    # Handling of properties that can also be specified as legacy "debugOptions" flags.
    # If property is explicitly set to false, but the flag is in "debugOptions", treat
    # it as an error. Returns None if the property wasn't explicitly set either way.
    def property_or_debug_option(prop_name, flag_name):
        assert prop_name[0].islower() and flag_name[0].isupper()

        value = request(prop_name, bool, optional=True)
        if value == ():
            value = None

        if flag_name in debug_options:
            if value is False:
                raise request.isnt_valid(
                    '{0!j}:false and "debugOptions":[{1!j}] are mutually exclusive',
                    prop_name,
                    flag_name,
                )
            value = True

        return value

    # "pythonPath" is a deprecated legacy spelling. If "python" is missing, then try
    # the alternative. But if both are missing, the error message should say "python".
    python_key = "python"
    if python_key in request:
        if "pythonPath" in request:
            raise request.isnt_valid(
                '"pythonPath" is not valid if "python" is specified'
            )
    elif "pythonPath" in request:
        python_key = "pythonPath"
    cmdline = request(python_key, json.array(unicode, vectorize=True, size=(0,)))
    if not len(cmdline):
        cmdline = [compat.filename(sys.executable)]

    if not request("noDebug", json.default(False)):
        port = request("port", int)
        cmdline += [
            compat.filename(os.path.dirname(debugpy.__file__)),
            "--connect",
            str(port),
        ]
        if not request("subProcess", True):
            cmdline += ["--configure-subProcess", "False"]
        adapter_access_token = request("adapterAccessToken", unicode, optional=True)
        if adapter_access_token != ():
            cmdline += ["--adapter-access-token", compat.filename(adapter_access_token)]
        debugpy_args = request("debugpyArgs", json.array(unicode))
        cmdline += debugpy_args

    # Use command line arguments propagated via launcher CLI, rather than "args", to get
    # their values after shell expansion in "runInTerminal" scenarios. The command line
    # parser in __main__ has already removed everything up to and including "--" by now.
    cmdline += sys.argv[1:]

    # We want the process name to reflect the target. So for -m, use the module name
    # that follows; otherwise use the first argument, which is either -c or filename.
    process_name = compat.filename(sys.argv[1] if sys.argv[1] != "-m" else sys.argv[2])

    env = os.environ.copy()
    env_changes = request("env", json.object(unicode))
    if sys.platform == "win32":
        # Environment variables are case-insensitive on Win32, so we need to normalize
        # both dicts to make sure that env vars specified in the debug configuration
        # overwrite the global env vars correctly. If debug config has entries that
        # differ in case only, that's an error.
        env = {k.upper(): v for k, v in os.environ.items()}
        n = len(env_changes)
        env_changes = {k.upper(): v for k, v in env_changes.items()}
        if len(env_changes) != n:
            raise request.isnt_valid('Duplicate entries in "env"')
    if "DEBUGPY_TEST" in env:
        # If we're running as part of a debugpy test, make sure that codecov is not
        # applied to the debuggee, since it will conflict with pydevd.
        env.pop("COV_CORE_SOURCE", None)
    env.update(env_changes)

    if request("gevent", False):
        env["GEVENT_SUPPORT"] = "True"

    console = request(
        "console",
        json.enum(
            "internalConsole", "integratedTerminal", "externalTerminal", optional=True
        ),
    )

    redirect_output = property_or_debug_option("redirectOutput", "RedirectOutput")
    if redirect_output is None:
        # If neither the property nor the option were specified explicitly, choose
        # the default depending on console type - "internalConsole" needs it to
        # provide any output at all, but it's unnecessary for the terminals.
        redirect_output = console == "internalConsole"
    if redirect_output:
        # sys.stdout buffering must be disabled - otherwise we won't see the output
        # at all until the buffer fills up.
        env["PYTHONUNBUFFERED"] = "1"
        # Force UTF-8 output to minimize data loss due to re-encoding.
        env["PYTHONIOENCODING"] = "utf-8"

    if property_or_debug_option("waitOnNormalExit", "WaitOnNormalExit"):
        if console == "internalConsole":
            raise request.isnt_valid(
                '"waitOnNormalExit" is not supported for "console":"internalConsole"'
            )
        debuggee.wait_on_exit_predicates.append(lambda code: code == 0)
    if property_or_debug_option("waitOnAbnormalExit", "WaitOnAbnormalExit"):
        if console == "internalConsole":
            raise request.isnt_valid(
                '"waitOnAbnormalExit" is not supported for "console":"internalConsole"'
            )
        debuggee.wait_on_exit_predicates.append(lambda code: code != 0)

    if sys.version_info < (3,):
        # Popen() expects command line and environment to be bytes, not Unicode.
        # Assume that values are filenames - it's usually either that, or numbers -
        # but don't allow encoding to fail if we guessed wrong.
        encode = functools.partial(compat.filename_bytes, errors="replace")
        cmdline = [encode(s) for s in cmdline]
        env = {encode(k): encode(v) for k, v in env.items()}

    debuggee.spawn(process_name, cmdline, env, redirect_output)
    return {}


def terminate_request(request):
    del debuggee.wait_on_exit_predicates[:]
    request.respond({})
    debuggee.kill()


def disconnect():
    del debuggee.wait_on_exit_predicates[:]
    debuggee.kill()
