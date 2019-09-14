# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, division, print_function, unicode_literals

import functools
import os
import platform
import sys

import ptvsd
from ptvsd.common import compat, fmt, json, messaging, sockets
from ptvsd.common.compat import unicode
from ptvsd.launcher import debuggee


channel = None
"""DAP message channel to the adapter."""


def connect(session_id, launcher_port):
    global channel
    assert channel is None

    sock = sockets.create_client()
    sock.connect(("127.0.0.1", launcher_port))

    stream = messaging.JsonIOStream.from_socket(sock, fmt("Adapter-{0}", session_id))
    channel = messaging.JsonMessageChannel(stream, handlers=Handlers())
    channel.start()


class Handlers(object):
    def launch_request(self, request):
        debug_options = set(request("debugOptions", json.array(unicode)))

        # Handling of properties that can also be specified as legacy "debugOptions" flags.
        # If property is explicitly set to false, but the flag is in "debugOptions", treat
        # it as an error.
        def property_or_debug_option(prop_name, flag_name):
            assert prop_name[0].islower() and flag_name[0].isupper()
            value = request(prop_name, json.default(flag_name in debug_options))
            if value is False and flag_name in debug_options:
                raise request.isnt_valid(
                    '{0!r}:false and "debugOptions":[{1!r}] are mutually exclusive',
                    prop_name,
                    flag_name,
                )
            return value

        cmdline = []
        if property_or_debug_option("sudo", "Sudo"):
            if platform.system() == "Windows":
                raise request.cant_handle('"sudo":true is not supported on Windows.')
            else:
                cmdline += ["sudo"]

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
        python = request(python_key, json.array(unicode, vectorize=True, size=(1,)))
        if not len(python):
            python = [compat.filename(sys.executable)]
        cmdline += python

        if not request("noDebug", json.default(False)):
            port = request("port", int)
            ptvsd_args = request("ptvsdArgs", json.array(unicode))
            cmdline += [
                compat.filename(os.path.dirname(ptvsd.__file__)),
                "--client",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ] + ptvsd_args

        program = module = code = ()
        if "program" in request:
            program = request("program", json.array(unicode, vectorize=True, size=(1,)))
            cmdline += program
            process_name = program[0]
        if "module" in request:
            module = request("module", json.array(unicode, vectorize=True, size=(1,)))
            cmdline += ["-m"] + module
            process_name = module[0]
        if "code" in request:
            code = request("code", json.array(unicode, vectorize=True, size=(1,)))
            cmdline += ["-c"] + code
            process_name = python[0]

        num_targets = len([x for x in (program, module, code) if x != ()])
        if num_targets == 0:
            raise request.isnt_valid(
                'either "program", "module", or "code" must be specified'
            )
        elif num_targets != 1:
            raise request.isnt_valid(
                '"program", "module", and "code" are mutually exclusive'
            )

        cmdline += request("args", json.array(unicode))

        cwd = request("cwd", unicode, optional=True)
        if cwd == ():
            # If it's not specified, but we're launching a file rather than a module,
            # and the specified path has a directory in it, use that.
            cwd = None if program == () else (os.path.dirname(program[0]) or None)

        env = os.environ.copy()
        if "PTVSD_TEST" in env:
            # If we're running as part of a ptvsd test, make sure that codecov is not
            # applied to the debuggee, since it will conflict with pydevd.
            env.pop("COV_CORE_SOURCE", None)
        env.update(request("env", json.object(unicode)))

        if request("gevent", False):
            env["GEVENT_SUPPORT"] = "True"

        redirect_output = "RedirectOutput" in debug_options
        if redirect_output:
            # sys.stdout buffering must be disabled - otherwise we won't see the output
            # at all until the buffer fills up.
            env["PYTHONUNBUFFERED"] = "1"

        if property_or_debug_option("waitOnNormalExit", "WaitOnNormalExit"):
            debuggee.wait_on_exit_predicates.append(lambda code: code == 0)
        if property_or_debug_option("waitOnAbnormalExit", "WaitOnAbnormalExit"):
            debuggee.wait_on_exit_predicates.append(lambda code: code != 0)

        if sys.version_info < (3,):
            # Popen() expects command line and environment to be bytes, not Unicode.
            # Assume that values are filenames - it's usually either that, or numbers -
            # but don't allow encoding to fail if we guessed wrong.
            encode = functools.partial(compat.filename_bytes, errors="replace")
            cmdline = [encode(s) for s in cmdline]
            env = {encode(k): encode(v) for k, v in env.items()}

        debuggee.spawn(process_name, cmdline, cwd, env, redirect_output)
        return {}

    def terminate_request(self, request):
        request.respond({})
        debuggee.kill()

    def disconnect(self):
        debuggee.kill()
