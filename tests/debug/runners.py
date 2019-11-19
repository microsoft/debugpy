# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, division, print_function, unicode_literals

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
    session.attach_by_socket("cli", log_dir="...")

    # Indirect invocation:
    run = runners.attach_by_socket
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

import os
import platform
import pytest
import sys

import ptvsd
from ptvsd.common import compat, fmt, log
from tests import net
from tests.debug import session


def _runner(f):
    assert f.__name__.startswith("launch") or f.__name__.startswith("attach")
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
                fmt("{0}={1}", k, v) for k, v in self._kwargs.items()
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
def launch(session, target, console="integratedTerminal", cwd=None):
    assert console in ("internalConsole", "integratedTerminal", "externalTerminal")

    log.info("Launching {0} in {1} using {2!j}.", target, session, console)

    target.configure(session)
    config = session.config
    config.setdefaults(
        {
            "console": "externalTerminal",
            "internalConsoleOptions": "neverOpen",
            "pythonPath": sys.executable,
        }
    )
    config["console"] = console
    if cwd is not None:
        config["cwd"] = cwd

    env = (
        session.spawn_adapter.env
        if config["console"] == "internalConsole"
        else config.env
    )
    target.cli(env)

    session.spawn_adapter()
    return session.request_launch()


def _attach_common_config(session, target, cwd):
    assert target.code is None or "debug_me" in target.code, fmt(
        "{0} must import debug_me.", target.filename
    )

    target.configure(session)
    config = session.config
    if cwd is not None:
        config.setdefault("pathMappings", [{"localRoot": cwd, "remoteRoot": "."}])
    return config


@_runner
def attach_by_pid(session, target, cwd=None, wait=True):
    if sys.version_info < (3,) and platform.system() == "Windows":
        pytest.skip("https://github.com/microsoft/ptvsd/issues/1811")

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
            debug_me = """
import sys
import threading
import time

while not "ptvsd" in sys.modules:
    time.sleep(0.1)

import ptvsd

while not ptvsd.is_attached():
    time.sleep(0.1)
    """
        else:
            debug_me = None

        session.spawn_debuggee(args, cwd=cwd, debug_me=debug_me)
        config["processId"] = session.debuggee.pid

    session.spawn_adapter()
    return session.request_attach()


@_runner
def attach_by_socket(
    session, target, method, listener="server", cwd=None, wait=True, log_dir=None
):
    log.info(
        "Attaching {0} to {1} by socket using {2}.", session, target, method.upper()
    )

    assert method in ("api", "cli")
    assert listener in ("server")  # TODO: ("adapter", "server")

    config = _attach_common_config(session, target, cwd)

    host = config["host"] = attach_by_socket.host
    port = config["port"] = attach_by_socket.port

    if method == "cli":
        args = [os.path.dirname(ptvsd.__file__)]
        if wait:
            args += ["--wait"]
        args += ["--host", compat.filename_str(host), "--port", str(port)]
        if log_dir is not None:
            args += ["--log-dir", log_dir]
        debug_me = None
    elif method == "api":
        args = []
        debug_me = """
import ptvsd
ptvsd.enable_attach(({host!r}, {port!r}), {args})
if {wait!r}:
    ptvsd.wait_for_attach()
"""
        attach_args = "" if log_dir is None else fmt("log_dir={0!r}", log_dir)
        debug_me = fmt(debug_me, host=host, port=port, wait=wait, args=attach_args)
    else:
        raise ValueError
    args += target.cli(session.spawn_debuggee.env)

    session.spawn_debuggee(args, cwd=cwd, debug_me=debug_me)
    if wait:
        session.wait_for_enable_attach()

    session.connect_to_adapter((host, port))
    return session.request_attach()


attach_by_socket.host = "127.0.0.1"
attach_by_socket.port = net.get_test_server_port(5678, 5800)

all_launch = [
    launch["internalConsole"],
    launch["integratedTerminal"],
    launch["externalTerminal"],
]

all_attach_by_socket = [attach_by_socket["api"], attach_by_socket["cli"]]

all_attach = all_attach_by_socket + [attach_by_pid]

all = all_launch + all_attach
