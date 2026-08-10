# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

"""Unit tests for debugpy.common.singleton.ThreadSafeSingleton locking."""

import pytest

from debugpy.common import singleton


class _Widget(singleton.ThreadSafeSingleton):
    """A trivial ThreadSafeSingleton subclass used to exercise assert_locked."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.value = 0


@pytest.fixture
def widget():
    # Use shared=False so each test gets a fresh, isolated instance without
    # colliding with any process-wide shared singleton of the same type.
    return _Widget(shared=False)


def test_assert_locked_passes_when_owned(widget):
    # Inside the with-statement, the current thread owns the lock, so
    # attribute access (which routes through assert_locked) must succeed.
    with widget:
        widget.value = 42
        assert widget.value == 42


def test_assert_locked_fails_when_unlocked(widget):
    # Outside any with-statement no thread owns the lock, so accessing a
    # non-threadsafe attribute must fail fast rather than silently proceed.
    with pytest.raises(AssertionError):
        widget.value

    with pytest.raises(AssertionError):
        widget.value = 1
