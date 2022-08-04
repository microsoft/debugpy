# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

"""Runners are recipes for executing Targets in a debug.Session.

Every function in this module that is decorated with @_runner must have at least two
positional arguments: (session, target) - and can have additional arguments. For every
such function, two artifacts are produced.

The function is exposed directly as a method on Session, with the session argument
becoming self.

The function is also exposed as a Runner object from this module. Runner objects are
callable, and invoke the wrapped function when called, but in addition, they can also
be bound to specific arguments, by using either [] or with_options(), which can be
chained arbitrarily::

    # Direct invocation:
    session.attach_connect("cli", log_dir="...")

    # Indirect invocation:
    run = runners.attach_connect
    run = run["cli"]
    run = run.with_options(log_dir="...")
    run(session, target)

runner[x][y][z] is just a convenient shorthand for binding positional arguments, same
as runner.with_options(x, y, z).

Runners are immutable, so every use of [] or with_options() creates a new runner with
the specified arguments bound. The runner must have all its required arguments bound
before it can be invoked.

Regardless of whether the runner is invoked directly on the Session, or via a Runner
object, if the start DAP sequence involves a configuration phase (the "initialized"
event and the "configurationDone" request), the runner must be used in a with-statement.
The statements inside the with-statement are executed after receiving the "initialized"
event, and before sending the "configurationDone" request::

    with run(session, target):
        # DAP requests can be made to session, but target is not running yet.
        session.set_breakpoints(...)
    # target is running now!

If there is no configuration phase, the runner returns directly::

    session.config["noDebug"] = True
    run(session, target)
    # target is running now!
"""

import contextlib
import os
import pytest
import sys

import debugpy
from debugpy.common import json, log
from tests import net, timeline
from tests.debug import session
from tests.patterns import some


def _runner(f):
    # assert f.__name__.startswith("launch") or f.__name__.startswith("attach")
    setattr(session.Session, f.__name__, f)

    class Runner(object):
        request = "launch" if f.__name__.startswith("launch") else "attach"

        def __init__(self, *args, **kwargs):
            self._args = tuple(args)
            self._kwargs = dict(kwargs)

        def __getattr__(self, name):
            return self._kwargs[name]

        def __call__(self, session, target, *args, **kwargs):
            if len(args) or len(kwargs):
                return self.with_options(*args, **kwargs)(session, target)
            return f(session, target, *self._args, **self._kwargs)

        def __iter__(self):
            # Since we implement __getitem__, iter() will assume that runners are
            # iterable, and will iterate over them by calling __getitem__ until it
            # raises IndexError - i.e. indefinitely. To prevent that, explicitly
            # implement __iter__ as unsupported.
            raise NotImplementedError

        def __getitem__(self, arg):
            return self.with_options(arg)

        def with_options(self, *args, **kwargs):
            new_args = self._args + args
            new_kwargs = dict(self._kwargs)
            new_kwargs.update(kwargs)
            return Runner(*new_args, **new_kwargs)

        def __repr__(self):
            result = type(self).__name__
            args = [str(x) for x in self._args] + [
                f"{k}={v}" for k, v in self._kwargs.items()
            ]
            if len(args):
                result += "(" + ", ".join(args) + ")"
            return result

        @property
        def pytest_id(self):
            return repr(self)

    Runner.__name__ = f.__name__
    return Runner()


@_runner
def launch(session, target, console=None, cwd=None):
    assert console in (
        None,
        "internalConsole",
        "integratedTerminal",
        "externalTerminal",
    )

    log.info("Launching {0} in {1} using {2}.", target, session, json.repr(console))

    target.configure(session)
    config = session.config
    config.setdefaults(
        {"console": "externalTerminal", "internalConsoleOptions": "neverOpen"}
    )
    if console is not None:
        config["console"] = console
    if cwd is not None:
        config["cwd"] = cwd
    if "python" not in config and "pythonPath" not in config:
        config["python"] = sys.executable

    env = (
        session.spawn_adapter.env
        if config["console"] == "internalConsole"
        else config.env
    )
    target.cli(env)

    session.spawn_adapter()
    return session.request_launch()


def _attach_common_config(session, target, cwd):
    assert (
        target.code is None or "debuggee.setup()" in target.code
    ), f"{target.filename} must invoke debuggee.setup()."

    target.configure(session)
    config = session.config
    if cwd is not None:
        config.setdefault("pathMappings", [{"localRoot": cwd, "remoteRoot": "."}])
    return config


@_runner
@contextlib.contextmanager
def attach_pid(session, target, cwd=None, wait=True):
    if wait and not sys.platform.startswith("linux"):
        pytest.skip("https://github.com/microsoft/ptvsd/issues/1926")

    log.info("Attaching {0} to {1} by PID.", session, target)

    config = session.config
    try:
        config["processId"] = int(target)
    except TypeError:
        pass

    if "processId" not in config:
        _attach_common_config(session, target, cwd)
        args = target.cli(session.spawn_debuggee.env)

        if wait:
            debuggee_setup = """
import sys
import threading
import time

while "debugpy" not in sys.modules:
    time.sleep(0.1)

from debuggee import scratchpad

while "_attach_pid" not in scratchpad:
    time.sleep(0.1)
    """
        else:
            debuggee_setup = None

        session.spawn_debuggee(args, cwd=cwd, setup=debuggee_setup)
        config["processId"] = session.debuggee.pid

    session.spawn_adapter()
    with session.request_attach():
        yield

    if wait:
        session.scratchpad["_attach_pid"] = True


@_runner
def attach_connect(session, target, method, cwd=None, wait=True, log_dir=None):
    log.info(
        "Attaching {0} to {1} by socket using {2}.", session, target, method.upper()
    )

    assert method in ("api", "cli")

    config = _attach_common_config(session, target, cwd)
    config["connect"] = {}
    config["connect"]["host"] = host = attach_connect.host
    config["connect"]["port"] = port = attach_connect.port

    if method == "cli":
        args = [
            os.path.dirname(debugpy.__file__),
            "--listen",
            f"{host}:{port}",
        ]
        if wait:
            args += ["--wait-for-client"]
        if log_dir is not None:
            args += ["--log-to", log_dir]
        if "subProcess" in config:
            args += ["--configure-subProcess", str(config["subProcess"])]
        debuggee_setup = None
    elif method == "api":
        args = []
        api_config = {k: v for k, v in config.items() if k in {"subProcess"}}
        debuggee_setup = """
import debugpy
if {log_dir!r}:
    debugpy.log_to({log_dir!r})
debugpy.configure({api_config!r})
debugpy.listen(({host!r}, {port!r}))
if {wait!r}:
    debugpy.wait_for_client()
"""
        debuggee_setup = debuggee_setup.format(
            host=host,
            port=port,
            wait=wait,
            log_dir=log_dir,
            api_config=api_config,
        )
    else:
        raise ValueError
    args += target.cli(session.spawn_debuggee.env)

    try:
        del config["subProcess"]
    except KeyError:
        pass

    session.spawn_debuggee(args, cwd=cwd, setup=debuggee_setup)
    session.wait_for_adapter_socket()
    session.connect_to_adapter((host, port))
    return session.request_attach()


attach_connect.host = "127.0.0.1"
attach_connect.port = net.get_test_server_port(5678, 5800)


@_runner
def attach_listen(session, target, method, cwd=None, log_dir=None):
    log.info(
        "Attaching {0} to {1} by socket using {2}.", session, target, method.upper()
    )

    assert method in ("api", "cli")

    config = _attach_common_config(session, target, cwd)
    config["listen"] = {}
    config["listen"]["host"] = host = attach_listen.host
    config["listen"]["port"] = port = attach_listen.port

    if method == "cli":
        args = [
            os.path.dirname(debugpy.__file__),
            "--connect",
            f"{host}:{port}",
        ]
        if log_dir is not None:
            args += ["--log-to", log_dir]
        if "subProcess" in config:
            args += ["--configure-subProcess", str(config["subProcess"])]
        debuggee_setup = None
    elif method == "api":
        args = []
        api_config = {k: v for k, v in config.items() if k in {"subProcess"}}
        debuggee_setup = f"""
import debugpy
if {log_dir!r}:
    debugpy.log_to({log_dir!r})
debugpy.configure({api_config!r})
debugpy.connect({(host, port)!r})
"""
    else:
        raise ValueError
    args += target.cli(session.spawn_debuggee.env)

    try:
        del config["subProcess"]
    except KeyError:
        pass

    def spawn_debuggee(occ):
        assert occ.body == some.dict.containing({"host": host, "port": port})
        session.spawn_debuggee(args, cwd=cwd, setup=debuggee_setup)

    session.timeline.when(timeline.Event("debugpyWaitingForServer"), spawn_debuggee)
    session.spawn_adapter(args=[] if log_dir is None else ["--log-dir", log_dir])
    return session.request_attach()


attach_listen.host = "127.0.0.1"
attach_listen.port = net.get_test_server_port(5478, 5600)

all_launch_terminal = [
    launch.with_options(console="integratedTerminal"),
    launch.with_options(console="externalTerminal"),
]

all_launch = [launch.with_options(console="internalConsole")] + all_launch_terminal

all_attach_listen = [attach_listen["api"], attach_listen["cli"]]

all_attach_connect = [attach_connect["api"], attach_connect["cli"]]

all_attach_socket = all_attach_listen + all_attach_connect

all_attach = all_attach_socket + [attach_pid]

all = all_launch + all_attach
