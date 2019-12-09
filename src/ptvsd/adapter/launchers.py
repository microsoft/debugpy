# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, division, print_function, unicode_literals

import os
import subprocess
import sys

from ptvsd import adapter, launcher
from ptvsd.common import compat, log, messaging
from ptvsd.adapter import components, servers


class Launcher(components.Component):
    """Handles the launcher side of a debug session."""

    message_handler = components.Component.message_handler

    def __init__(self, session, stream):
        with session:
            assert not session.launcher
            super(Launcher, self).__init__(session, stream)

            self.pid = None
            """Process ID of the debuggee process, as reported by the launcher."""

            self.exit_code = None
            """Exit code of the debuggee process."""

            session.launcher = self

    @message_handler
    def process_event(self, event):
        self.pid = event("systemProcessId", int)
        self.ide.propagate_after_start(event)

    @message_handler
    def output_event(self, event):
        self.ide.propagate_after_start(event)

    @message_handler
    def exited_event(self, event):
        self.exit_code = event("exitCode", int)
        # We don't want to tell the IDE about this just yet, because it will then
        # want to disconnect, and the launcher might still be waiting for keypress
        # (if wait-on-exit was enabled). Instead, we'll report the event when we
        # receive "terminated" from the launcher, right before it exits.

    @message_handler
    def terminated_event(self, event):
        self.ide.channel.send_event("exited", {"exitCode": self.exit_code})
        self.channel.close()


def spawn_debuggee(session, start_request, sudo, args, console, console_title):
    cmdline = ["sudo"] if sudo else []
    cmdline += [sys.executable, os.path.dirname(launcher.__file__)]
    cmdline += args
    env = {}

    def spawn_launcher():
        with session.accept_connection_from_launcher() as (_, launcher_port):
            env[str("PTVSD_LAUNCHER_PORT")] = str(launcher_port)
            if log.log_dir is not None:
                env[str("PTVSD_LOG_DIR")] = compat.filename_str(log.log_dir)
            if log.stderr.levels != {"warning", "error"}:
                env[str("PTVSD_LOG_STDERR")] = " ".join(log.log_stderr)

            if console == "internalConsole":
                log.info("{0} spawning launcher: {1!r}", session, cmdline)

                # If we are talking to the IDE over stdio, sys.stdin and sys.stdout are
                # redirected to avoid mangling the DAP message stream. Make sure the
                # launcher also respects that.
                subprocess.Popen(
                    cmdline,
                    env=dict(list(os.environ.items()) + list(env.items())),
                    stdin=sys.stdin,
                    stdout=sys.stdout,
                    stderr=sys.stderr,
                )

            else:
                log.info('{0} spawning launcher via "runInTerminal" request.', session)
                session.ide.capabilities.require("supportsRunInTerminalRequest")
                kinds = {
                    "integratedTerminal": "integrated",
                    "externalTerminal": "external",
                }
                session.ide.channel.request(
                    "runInTerminal",
                    {
                        "kind": kinds[console],
                        "title": console_title,
                        "args": cmdline,
                        "env": env,
                    },
                )

        try:
            session.launcher.channel.request(start_request.command, arguments)
        except messaging.MessageHandlingError as exc:
            exc.propagate(start_request)

    if session.no_debug:
        arguments = start_request.arguments
        spawn_launcher()
    else:
        _, port = servers.Connection.listener.getsockname()
        arguments = dict(start_request.arguments)
        arguments["port"] = port
        arguments["clientAccessToken"] = adapter.access_token
        spawn_launcher()

        if not session.wait_for(
            lambda: session.launcher is not None and session.launcher.pid is not None,
            timeout=5,
        ):
            raise start_request.cant_handle(
                '{0} timed out waiting for "process" event from {1}',
                session,
                session.launcher,
            )

        # Wait for the first incoming connection regardless of the PID - it won't
        # necessarily match due to the use of stubs like py.exe or "conda run".
        conn = servers.wait_for_connection(session, lambda conn: True, timeout=10)
        if conn is None:
            raise start_request.cant_handle(
                "{0} timed out waiting for debuggee to spawn", session
            )
        conn.attach_to_session(session)
