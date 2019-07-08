# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

"""Tracks the overall state of the adapter, and enforces valid state transitions.
"""

from ptvsd.common import log, singleton


# Order defines valid transitions.
STATES = (
    "starting",  # before "initialize" is received
    "initializing",  # until "initialized" is sent
    "configuring",  # until "configurationDone" is received
    "running",  # until "disconnect" or "terminate" is received
    "shutting_down",  # until the adapter process exits
)


class State(singleton.ThreadSafeSingleton):
    _state = STATES[0]

    @property
    @singleton.autolocked_method
    def state(self):
        return self._state

    @state.setter
    @singleton.autolocked_method
    def state(self, new_state):
        assert STATES.index(self._state) < STATES.index(new_state)
        log.debug("Adapter state changed from {0!r} to {1!r}", self._state, new_state)
        self._state = new_state


def current():
    return State().state


def change(new_state):
    State().state = new_state
