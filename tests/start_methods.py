# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals


import os
import ptvsd
import psutil
import py.path
import pytest
import subprocess
import sys
import time

from ptvsd.common import compat, fmt, json, log
from ptvsd.common.compat import unicode
from tests import helpers, net, watchdog
from tests.patterns import some


PTVSD_DIR = py.path.local(ptvsd.__file__) / ".."
PTVSD_PORT = net.get_test_server_port(5678, 5800)

# Code that is injected into the debuggee process when it does `import debug_me`,
# and start_method is attach_socket_*
PTVSD_DEBUG_ME = """
import ptvsd
ptvsd.enable_attach(("127.0.0.1", {ptvsd_port}), log_dir={log_dir})
ptvsd.wait_for_attach()
"""


class DebugStartBase(object):
    ignore_unobserved = []

    def __init__(self, session, method="base"):
        self.session = session
        self.method = method
        self.captured_output = helpers.CapturedOutput(self.session)
        self.debuggee_process = None
        self.expected_exit_code = None

    def start_debugging(self, **kwargs):
        pass

    def wait_for_debuggee(self):
        # TODO: Exit should not be restricted to launch tests only
        if self.expected_exit_code is not None and 'launch' in self.method:
            exited = self.session.wait_for_next_event("exited", freeze=False)
            assert exited == some.dict.containing({"exitCode": self.expected_exit_code})

        self.session.wait_for_next_event("terminated")

        if self.debuggee_process is None:
            return

        try:
            self.debuggee_process.wait()
        except Exception:
            pass
        finally:
            watchdog.unregister_spawn(
                self.debuggee_process.pid, self.session.debuggee_id
            )

    def run_in_terminal(self, request, **kwargs):
        raise request.isnt_valid("not supported")

    def _build_common_args(
        self,
        args,
        showReturnValue=None,
        justMyCode=True,
        subProcess=None,
        django=None,
        jinja=None,
        flask=None,
        pyramid=None,
        logToFile=None,
        redirectOutput=True,
        noDebug=None,
        maxExceptionStackFrames=None,
        steppingResumesAllThreads=None,
        rules=None,
        successExitCodes=None,
    ):
        if logToFile:
            args["logToFile"] = logToFile
            if "env" in args:
                args["env"]["PTVSD_LOG_DIR"] = self.session.log_dir

        if showReturnValue:
            args["showReturnValue"] = showReturnValue
            args["debugOptions"] += ["ShowReturnValue"]

        if redirectOutput:
            args["redirectOutput"] = redirectOutput
            args["debugOptions"] += ["RedirectOutput"]

        if justMyCode is False:
            # default behavior is Just-my-code = true
            args["justMyCode"] = justMyCode
            args["debugOptions"] += ["DebugStdLib"]

        if django:
            args["django"] = django
            args["debugOptions"] += ["Django"]

        if jinja:
            args["jinja"] = jinja
            args["debugOptions"] += ["Jinja"]

        if flask:
            args["flask"] = flask
            args["debugOptions"] += ["Flask"]

        if pyramid:
            args["pyramid"] = pyramid
            args["debugOptions"] += ["Pyramid"]

        # VS Code uses noDebug in both attach and launch cases. Even though
        # noDebug on attach does not make any sense.
        if noDebug:
            args["noDebug"] = True

        if subProcess:
            args["subProcess"] = subProcess
            args["debugOptions"] += ["Multiprocess"]

        if maxExceptionStackFrames:
            args["maxExceptionStackFrames"] = maxExceptionStackFrames

        if steppingResumesAllThreads:
            args["steppingResumesAllThreads"] = steppingResumesAllThreads

        if rules is not None:
            args["rules"] = rules

        if successExitCodes:
            args["successExitCodes"] = successExitCodes

    def __str__(self):
        return self.method


class Launch(DebugStartBase):
    def __init__(self, session):
        super(Launch, self).__init__(session, "launch")
        self._launch_args = None

    def _build_launch_args(
        self,
        launch_args,
        run_as,
        target,
        pythonPath=sys.executable,
        args=(),
        cwd=None,
        env=None,
        stopOnEntry=None,
        gevent=None,
        sudo=None,
        waitOnNormalExit=None,
        waitOnAbnormalExit=None,
        breakOnSystemExitZero=None,
        console="externalTerminal",
        internalConsoleOptions="neverOpen",
        **kwargs
    ):
        assert console in ("internalConsole", "integratedTerminal", "externalTerminal")
        env = {} if env is None else dict(env)
        debug_options = []
        launch_args.update(
            {
                "name": "Terminal",
                "type": "python",
                "request": "launch",
                "console": console,
                "env": env,
                "pythonPath": pythonPath,
                "args": args,
                "internalConsoleOptions": internalConsoleOptions,
                "debugOptions": debug_options,
            }
        )

        if stopOnEntry:
            launch_args["stopOnEntry"] = stopOnEntry
            debug_options += ["StopOnEntry"]

        if gevent:
            launch_args["gevent"] = gevent
            env["GEVENT_SUPPORT"] = "True"

        if sudo:
            launch_args["sudo"] = sudo

        if waitOnNormalExit:
            debug_options += ["WaitOnNormalExit"]

        if waitOnAbnormalExit:
            debug_options += ["WaitOnAbnormalExit"]

        if breakOnSystemExitZero:
            debug_options += ["BreakOnSystemExitZero"]

        target_str = target
        if isinstance(target, py.path.local):
            target_str = target.strpath

        if cwd:
            launch_args["cwd"] = cwd
        elif os.path.isfile(target_str) or os.path.isdir(target_str):
            launch_args["cwd"] = os.path.dirname(target_str)
        else:
            launch_args["cwd"] = os.getcwd()

        if "PYTHONPATH" not in env:
            env["PYTHONPATH"] = ""

        if run_as == "program":
            launch_args["program"] = target_str
        elif run_as == "module":
            if os.path.isfile(target_str) or os.path.isdir(target_str):
                env["PYTHONPATH"] += os.pathsep + os.path.dirname(target_str)
                try:
                    launch_args["module"] = target_str[
                        (len(os.path.dirname(target_str)) + 1) : -3
                    ]
                except Exception:
                    launch_args["module"] = "code_to_debug"
            else:
                launch_args["module"] = target_str
        elif run_as == "code":
            with open(target_str, "rb") as f:
                launch_args["code"] = f.read().decode("utf-8")
        else:
            pytest.fail()

        self._build_common_args(launch_args, **kwargs)
        return launch_args

    def _wait_for_process_event(self):
        process_body = self.session.wait_for_next_event("process", freeze=False)
        assert process_body == {
            "name": some.str,
            "isLocalProcess": True,
            "startMethod": "launch",
            "systemProcessId": some.int,
        }
        return process_body

    def configure(self, run_as, target, **kwargs):
        self._launch_args = self._build_launch_args({}, run_as, target, **kwargs)
        self.no_debug = self._launch_args.get("noDebug", False)

        if not self.no_debug:
            self._launch_request = self.session.send_request(
                "launch", self._launch_args
            )
            self.session.wait_for_next_event("initialized")

    def start_debugging(self):
        if self.no_debug:
            self._launch_request = self.session.send_request(
                "launch", self._launch_args
            )
        else:
            self.session.request("configurationDone")

        self._launch_request.wait_for_response(freeze=False)
        self._wait_for_process_event()

    def run_in_terminal(self, request):
        args = request("args", json.array(unicode))
        cwd = request("cwd", unicode)

        env = os.environ.copy()
        env.update(request("env", json.object(unicode)))

        if sys.version_info < (3,):
            args = [compat.filename_str(s) for s in args]
            env = {
                compat.filename_str(k): compat.filename_str(v) for k, v in env.items()
            }

        log.info(
            '{0} spawning {1} via "runInTerminal" request',
            self.session,
            self.session.debuggee_id,
        )
        self.debuggee_process = psutil.Popen(
            args,
            cwd=cwd,
            env=env,
            bufsize=0,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        watchdog.register_spawn(self.debuggee_process.pid, self.session.debuggee_id)
        self.captured_output.capture(self.debuggee_process)
        return {}


class AttachBase(DebugStartBase):
    ignore_unobserved = DebugStartBase.ignore_unobserved + []

    def __init__(self, session, name):
        super(AttachBase, self).__init__(session, name)
        self._attach_args = {}

    def _build_attach_args(
        self,
        attach_args,
        run_as,
        target,
        host="127.0.0.1",
        port=PTVSD_PORT,
        pathMappings=None,
        **kwargs
    ):
        assert host is not None
        assert port is not None
        debug_options = []
        attach_args.update(
            {
                "name": "Attach",
                "type": "python",
                "request": "attach",
                "debugOptions": debug_options,
            }
        )

        attach_args["host"] = host
        attach_args["port"] = port

        if pathMappings is not None:
            attach_args["pathMappings"] = pathMappings

        self._build_common_args(attach_args, **kwargs)
        return attach_args

    def configure(self, run_as, target, **kwargs):
        target_str = target
        if isinstance(target, py.path.local):
            target_str = target.strpath

        env = os.environ.copy()
        env.update(kwargs["env"])

        cli_args = kwargs.get("cli_args")
        if run_as == "program":
            cli_args += [target_str]
        elif run_as == "module":
            if os.path.isfile(target_str) or os.path.isdir(target_str):
                env["PYTHONPATH"] += os.pathsep + os.path.dirname(target_str)
                try:
                    module = target_str[(len(os.path.dirname(target_str)) + 1) : -3]
                except Exception:
                    module = "code_to_debug"
            else:
                module = target_str
            cli_args += ["-m", module]
        elif run_as == "code":
            with open(target_str, "rb") as f:
                cli_args += ["-c", f.read()]
        else:
            pytest.fail()

        cli_args += kwargs.get("args")
        cli_args = [compat.filename_str(s) for s in cli_args]

        cwd = kwargs.get("cwd")
        if cwd:
            pass
        elif os.path.isfile(target_str) or os.path.isdir(target_str):
            cwd = os.path.dirname(target_str)
        else:
            cwd = os.getcwd()

        if "pathMappings" not in self._attach_args:
            self._attach_args["pathMappings"] = [{"localRoot": cwd, "remoteRoot": "."}]

        env_str = "\n".join((fmt("    {0}={1}", k, env[k]) for k in sorted(env.keys())))
        log.info(
            "Spawning {0}: {1!j}\n\n" "with cwd:\n    {2!j}\n\n" "with env:\n{3}",
            self.session.debuggee_id,
            cli_args,
            cwd,
            env_str,
        )
        self.debuggee_process = subprocess.Popen(
            cli_args,
            cwd=cwd,
            env=env,
            bufsize=0,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        watchdog.register_spawn(self.debuggee_process.pid, self.session.debuggee_id)
        self.captured_output.capture(self.debuggee_process)

        connected = False
        pid = self.debuggee_process.pid
        while connected is False:
            time.sleep(0.1)
            connections = psutil.net_connections()
            connected = (
                len(list(p for (_, _, _, _, _, _, p) in connections if p == pid)) > 0
            )

        self._attach_request = self.session.send_request("attach", self._attach_args)
        self.session.wait_for_next_event("initialized")

    def start_debugging(self):
        self.session.request("configurationDone")

        self.no_debug = self._attach_args.get("noDebug", False)
        if self.no_debug:
            log.info('{0} ignoring "noDebug" in "attach"', self.session)

        process_body = self.session.wait_for_next_event("process")
        assert process_body == some.dict.containing(
            {
                "name": some.str,
                "isLocalProcess": True,
                "startMethod": "attach",
                "systemProcessId": some.int,
            }
        )

        self._attach_request.wait_for_response()


class AttachSocketImport(AttachBase):
    def __init__(self, session):
        super(AttachSocketImport, self).__init__(session, "attach_socket_import")

    def _check_ready_for_import(self, path_or_code):
        if isinstance(path_or_code, py.path.local):
            path_or_code = path_or_code.strpath

        if os.path.isfile(path_or_code):
            with open(path_or_code, "rb") as f:
                code = f.read()
        elif "\n" in path_or_code:
            code = path_or_code
        else:
            # path_or_code is a module name
            return
        assert b"debug_me" in code, fmt(
            "{0} is started via {1}, but it doesn't import debug_me.",
            path_or_code,
            self.method,
        )

    def configure(
        self,
        run_as,
        target,
        pythonPath=sys.executable,
        args=(),
        cwd=None,
        env=None,
        **kwargs
    ):
        env = {} if env is None else dict(env)
        self._attach_args = self._build_attach_args({}, run_as, target, **kwargs)

        ptvsd_port = self._attach_args["port"]
        log_dir = None
        if self._attach_args.get("logToFile", False):
            log_dir = '"' + self.session.log_dir + '"'

        env["PTVSD_DEBUG_ME"] = fmt(
            PTVSD_DEBUG_ME, ptvsd_port=ptvsd_port, log_dir=log_dir
        )

        self._check_ready_for_import(target)

        cli_args = [pythonPath]
        super(AttachSocketImport, self).configure(
            run_as, target, cwd=cwd, env=env, args=args, cli_args=cli_args, **kwargs
        )


class AttachSocketCmdLine(AttachBase):
    def __init__(self, session):
        super(AttachSocketCmdLine, self).__init__(session, "attach_socket_cmdline")

    def configure(
        self,
        run_as,
        target,
        pythonPath=sys.executable,
        args=[],
        cwd=None,
        env=None,
        **kwargs
    ):
        env = {} if env is None else dict(env)
        self._attach_args = self._build_attach_args({}, run_as, target, **kwargs)

        cli_args = [pythonPath]
        cli_args += [PTVSD_DIR.strpath]
        cli_args += ["--wait"]
        cli_args += [
            "--host",
            self._attach_args["host"],
            "--port",
            str(self._attach_args["port"]),
        ]

        log_dir = (
            self.session.log_dir if self._attach_args.get("logToFile", False) else None
        )
        if log_dir:
            cli_args += ["--log-dir", log_dir]

        if self._attach_args.get("multiprocess", False):
            cli_args += ["--multiprocess"]

        super(AttachSocketCmdLine, self).configure(
            run_as, target, cwd=cwd, env=env, args=args, cli_args=cli_args, **kwargs
        )


class AttachProcessId(DebugStartBase):
    def __init__(self, session):
        super().__init__(session, "attach_pid")


class CustomServer(DebugStartBase):
    def __init__(self, session):
        super().__init__(session, "custom_server")


class CustomClient(DebugStartBase):
    def __init__(self, session):
        super().__init__(session, "custom_client")


__all__ = [
    Launch,  # ptvsd --client ... foo.py
    AttachSocketCmdLine,  #  ptvsd ... foo.py
    AttachSocketImport,  #  python foo.py (foo.py must import debug_me)
    AttachProcessId,  # python foo.py && ptvsd ... --pid
    CustomClient,  # python foo.py (foo.py has to manually call ptvsd.attach)
    CustomServer,  # python foo.py (foo.py has to manually call ptvsd.enable_attach)
]
