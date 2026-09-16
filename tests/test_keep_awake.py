"""Tests for the sleep-prevention helper. Windows-specific by nature (it
wraps a Win32 API) - on any other platform it's a documented, safe no-op."""
import sys

from airam_lights.keep_awake import allow_sleep, prevent_sleep


def test_prevent_and_allow_sleep_do_not_raise():
    # Real call: on Windows this actually asserts/releases the OS-level
    # hold (idempotent and harmless to call repeatedly in a test), on any
    # other platform it's a no-op that returns False.
    result = prevent_sleep()
    if sys.platform == "win32":
        assert result is True
    else:
        assert result is False
    allow_sleep()  # must never raise, regardless of platform


def test_prevent_sleep_is_safe_to_call_multiple_times():
    for _ in range(3):
        prevent_sleep()
    allow_sleep()
