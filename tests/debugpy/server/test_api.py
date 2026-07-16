# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

"""Unit tests for debugpy.server.api behaviors that don't require a live session."""

import pytest

from debugpy.server import api


@pytest.fixture
def reset_settrace_called():
    """Isolate the global _settrace.called latch used by configure()."""
    original = api._settrace.called
    api._settrace.called = False
    try:
        yield
    finally:
        api._settrace.called = original


def test_settrace_failure_does_not_block_configure(monkeypatch, reset_settrace_called):
    # ensure_logging() writes log files; stub it out for this unit test.
    monkeypatch.setattr(api, "ensure_logging", lambda: None)

    def failing_settrace(*args, **kwargs):
        raise RuntimeError("settrace failed")

    monkeypatch.setattr(api.pydevd, "settrace", failing_settrace)

    with pytest.raises(RuntimeError, match="settrace failed"):
        api._settrace()

    # A failed settrace must not latch `called`, ...
    assert api._settrace.called is False

    # ... so configure() must not reject the call as "already running".
    api.configure()


def test_settrace_success_blocks_configure(monkeypatch, reset_settrace_called):
    monkeypatch.setattr(api, "ensure_logging", lambda: None)
    monkeypatch.setattr(api.pydevd, "settrace", lambda *args, **kwargs: None)

    api._settrace()
    assert api._settrace.called is True

    with pytest.raises(RuntimeError, match="already running"):
        api.configure()
