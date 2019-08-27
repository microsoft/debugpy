# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

from ptvsd.adapter import components


class Launcher(components.Component):
    """Handles the launcher side of a debug session."""

    message_handler = components.Component.message_handler

    def __init__(self, session, stream):
        super(Launcher, self).__init__(session, stream)

        self.pid = None
        """Process ID of the debuggee process, as reported by the launcher."""

        self.exit_code = None
        """Exit code of the debuggee process."""

        assert not session.launcher
        session.launcher = self

    @message_handler
    def process_event(self, event):
        self.pid = event("systemProcessId", int)
        assert self.session.pid is None
        self.session.pid = self.pid
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
