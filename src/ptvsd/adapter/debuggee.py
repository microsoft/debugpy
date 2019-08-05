# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

"""Manages the lifetime of the debugged process and its subprocesses, in scenarios
where it is controlled by the adapter (i.e. "launch").
"""

import atexit
import collections
import os
import platform
import signal
import subprocess
import sys
import threading

import ptvsd.__main__
from ptvsd.adapter import channels, contract
from ptvsd.common import compat, fmt, json, launcher, messaging, log, singleton
from ptvsd.common.compat import unicode


terminate_at_exit = True
"""Whether the debuggee process should be terminated when the adapter process exits,
or allowed to continue running.
"""

exit_code = None
"""The exit code of the debuggee process, once it has terminated."""

pid = None
"""Debuggee process ID."""

_got_pid = threading.Event()
"""A threading.Event that is set when pid is set.
"""

_exited = None
"""A threading.Event that is set when the debuggee process exits.

Created when the process is spawned.
"""


SpawnInfo = collections.namedtuple(
    "SpawnInfo", ["console", "console_title", "cmdline", "cwd", "env"]
)


def spawn_and_connect(request):
    """Spawns the process as requested by the DAP "launch" request, with the debug
    server running inside the process; and connects to that server. Returns the
    server channel.

    Caller is responsible for calling start() on the returned channel.
    """

    channel = channels.Channels().accept_connection_from_server(
        ("127.0.0.1", 0),
        before_accept=lambda address: _parse_request_and_spawn(request, address),
    )
    return channel


def _parse_request_and_spawn(request, address):
    spawn_info = _parse_request(request, address)
    log.debug(
        "SpawnInfo = {0!j}",
        collections.OrderedDict(
            {
                "console": spawn_info.console,
                "cwd": spawn_info.cwd,
                "cmdline": spawn_info.cmdline,
                "env": spawn_info.env,
            }
        ),
    )

    spawn = {
        "internalConsole": _spawn_popen,
        "integratedTerminal": _spawn_terminal,
        "externalTerminal": _spawn_terminal,
    }[spawn_info.console]

    global _exited
    _exited = threading.Event()
    try:
        spawn(request, spawn_info)
    finally:
        if pid is None:
            _exited.set()
        else:
            atexit.register(lambda: terminate() if terminate_at_exit else None)


def _parse_request(request, address):
    """Parses a "launch" request and returns SpawnInfo for it.

    address is (host, port) on which the adapter listener is waiting for connection
    from the debug server.
    """

    assert request.is_request("launch")
    host, port = address
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

    console = request(
        "console",
        json.enum(
            "internalConsole", "integratedTerminal", "externalTerminal", optional=True
        ),
    )
    if console != "internalConsole":
        if not contract.ide.capabilities["supportsRunInTerminalRequest"]:
            raise request.cant_handle(
                'Unable to launch via "console":{0!j}, because the IDE is does not '
                'have the "supportsRunInTerminalRequest" capability',
                console,
            )

    console_title = request("consoleTitle", json.default("Python Debug Console"))

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
        python = [sys.executable]
    cmdline += python

    cmdline += [compat.filename(launcher.__file__)]
    if property_or_debug_option("waitOnNormalExit", "WaitOnNormalExit"):
        cmdline += ["--wait-on-normal"]
    if property_or_debug_option("waitOnAbnormalExit", "WaitOnAbnormalExit"):
        cmdline += ["--wait-on-abnormal"]

    ptvsd_args = request("ptvsdArgs", json.array(unicode))
    cmdline += [
        "--",
        compat.filename(ptvsd.__main__.__file__),
        "--client",
        "--host",
        host,
        "--port",
        str(port),
    ] + ptvsd_args

    program = module = code = ()
    if "program" in request:
        program = request("program", json.array(unicode, vectorize=True, size=(1,)))
        cmdline += program
    if "module" in request:
        module = request("module", json.array(unicode, vectorize=True, size=(1,)))
        cmdline += ["-m"]
        cmdline += module
    if "code" in request:
        code = request("code", json.array(unicode, vectorize=True, size=(1,)))
        cmdline += ["-c"]
        cmdline += code

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
        cwd = None if program == () else (os.path.dirname(program) or None)

    env = request("env", json.object(unicode))

    return SpawnInfo(console, console_title, cmdline, cwd, env)


def _spawn_popen(request, spawn_info):
    env = os.environ.copy()
    env.update(spawn_info.env)

    try:
        proc = subprocess.Popen(spawn_info.cmdline, cwd=spawn_info.cwd, env=env)
    except Exception as exc:
        raise request.cant_handle(
            "Error launching process: {0}\n\nCommand line:{1!r}",
            exc,
            spawn_info.cmdline,
        )

    log.info("Spawned debuggee process with PID={0}.", proc.pid)

    global pid
    try:
        pid = proc.pid
        _got_pid.set()
        ProcessTracker().track(pid)
    except Exception:
        # If we can't track it, we won't be able to terminate it if asked; but aside
        # from that, it does not prevent debugging.
        log.exception(
            "Unable to track debuggee process with PID={0}.", pid, category="warning"
        )

    # Wait directly on the Popen object, instead of going via ProcessTracker. This is
    # more reliable on Windows, because Popen always has the correct process handle
    # that it gets from CreateProcess, whereas ProcessTracker will use OpenProcess to
    # get it from PID, and there's a race condition there if the process dies and its
    # PID is reused before OpenProcess is called.
    def wait_for_exit():
        global exit_code
        try:
            exit_code = proc.wait()
        except Exception:
            log.exception("Couldn't determine process exit code:")
            exit_code = -1
        finally:
            _exited.set()

    wait_thread = threading.Thread(target=wait_for_exit, name='"launch" worker')
    wait_thread.start()


def _spawn_terminal(request, spawn_info):
    kinds = {"integratedTerminal": "integrated", "externalTerminal": "external"}
    body = {
        "kind": kinds[spawn_info.console],
        "title": spawn_info.console_title,
        "cwd": spawn_info.cwd,
        "args": spawn_info.cmdline,
        "env": spawn_info.env,
    }

    try:
        channels.Channels().ide().request("runInTerminal", body)
    except messaging.MessageHandlingError as exc:
        exc.propagate(request)

    # Although "runInTerminal" response has "processId", it's optional, and in practice
    # it is not used by VSCode: https://github.com/microsoft/vscode/issues/61640.
    # Thus, we can only retrieve the PID via the "process" event, and only then we can
    # start tracking it. Until then, nothing else to do.
    pass


def parse_pid(process_event):
    assert process_event.is_event("process")

    if _got_pid.is_set():
        # If we already have the PID, there's nothing to do.
        return

    global pid
    sys_pid = process_event("systemProcessId", int)

    def after_exit(code):
        global exit_code
        exit_code = code
        _exited.set()

    try:
        pid = sys_pid
        _got_pid.set()
        ProcessTracker().track(pid, after_exit=after_exit)
    except Exception as exc:
        # If we can't track it, we won't be able to detect if it exited or retrieve
        # the exit code, so fail immediately.
        raise process_event.cant_handle(
            "Couldn't get debuggee process handle: {0}", str(exc)
        )


def wait_for_pid(timeout=None):
    """Waits for debuggee PID to be determined.

    Returns True if PID was determined, False if the wait timed out. If it returned
    True, then pid is guaranteed to be set.
    """
    return _got_pid.wait(timeout)


def wait_for_exit(timeout=None):
    """Waits for the debugee process to exit.

    Returns True if the process exited, False if the wait timed out. If it returned
    True, then exit_code is guaranteed to be set.
    """

    if pid is None:
        # Debugee was launched with "runInTerminal", but the debug session fell apart
        # before we got a "process" event and found out what its PID is. It's not a
        # fatal error, but there's nothing to wait on. Debuggee process should have
        # exited (or crashed) by now in any case.
        return

    assert _exited is not None
    timed_out = not _exited.wait(timeout)
    if not timed_out:
        # ProcessTracker will stop tracking it by itself, but it might take a bit
        # longer for it to notice that the process is gone. If killall() is invoked
        # before that, it will try to kill that non-existing process, and log the
        # resulting error. This prevents that.
        ProcessTracker().stop_tracking(pid)
    return not timed_out


def terminate(after=0):
    """Waits for the debugee process to exit for the specified number of seconds. If
    the process or any subprocesses are still alive after that time, force-kills them.

    If any errors occur while trying to kill any process, logs and swallows them.

    If the debugee process hasn't been spawned yet, does nothing.
    """

    if _exited is None:
        return

    wait_for_exit(after)
    ProcessTracker().killall()


def register_subprocess(pid):
    """Registers a subprocess of the debuggee process."""
    ProcessTracker().track(pid)


class ProcessTracker(singleton.ThreadSafeSingleton):
    """Tracks processes that belong to the debuggee.
    """

    _processes = {}
    """Keys are PIDs, and values are handles as used by os.waitpid(). On Windows,
    handles are distinct. On all other platforms, the PID is also the handle.
    """

    _exit_codes = {}
    """Keys are PIDs, values are exit codes."""

    @singleton.autolocked_method
    def track(self, pid, after_exit=lambda _: None):
        """Starts tracking the process with the specified PID, and returns its handle.

        If the process exits while it is still being tracked, after_exit is invoked
        with its exit code.
        """

        # Register the atexit handler only once, on the first tracked process.
        if not len(self._processes):
            atexit.register(lambda: self.killall() if terminate_at_exit else None)

        self._processes[pid] = handle = _pid_to_handle(pid)
        log.debug(
            "Tracking debuggee process with PID={0} and HANDLE=0x{1:08X}.", pid, handle
        )

        def wait_for_exit():
            try:
                _, exit_code = os.waitpid(handle, 0)
            except Exception:
                exit_code = -1
                log.exception(
                    "os.waitpid() for debuggee process with HANDLE=0x{1:08X} failed:",
                    handle,
                )
            else:
                exit_code >>= 8
                log.info(
                    "Debuggee process with PID={0} exited with exitcode {1}.",
                    pid,
                    exit_code,
                )

            with self:
                if pid in self._processes:
                    self._exit_codes[pid] = exit_code
                    self.stop_tracking(pid)
                    after_exit(exit_code)

        wait_thread = threading.Thread(
            target=wait_for_exit, name=fmt("Process(pid={0}) tracker", pid)
        )
        wait_thread.daemon = True
        wait_thread.start()

        return handle

    @singleton.autolocked_method
    def stop_tracking(self, pid):
        if self._processes.pop(pid, None) is not None:
            log.debug("Stopped tracking debuggee process with PID={0}.", pid)

    @singleton.autolocked_method
    def killall(self):
        pids = list(self._processes.keys())
        for pid in pids:
            log.info("Killing debuggee process with PID={0}.", pid)
            try:
                os.kill(pid, signal.SIGTERM)
            except Exception:
                log.exception("Couldn't kill debuggee process with PID={0}:", pid)


if platform.system() != "Windows":
    _pid_to_handle = lambda pid: pid
else:
    import ctypes
    from ctypes import wintypes

    class ProcessAccess(wintypes.DWORD):
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        SYNCHRONIZE = 0x100000

    OpenProcess = ctypes.windll.kernel32.OpenProcess
    OpenProcess.restype = wintypes.HANDLE
    OpenProcess.argtypes = (ProcessAccess, wintypes.BOOL, wintypes.DWORD)

    def _pid_to_handle(pid):
        handle = OpenProcess(
            ProcessAccess.PROCESS_QUERY_LIMITED_INFORMATION | ProcessAccess.SYNCHRONIZE,
            False,
            pid,
        )
        if not handle:
            raise ctypes.WinError()
        return handle
