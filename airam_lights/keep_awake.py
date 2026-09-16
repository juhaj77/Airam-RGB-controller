"""Prevents Windows from putting the PC to sleep while one of these apps is
running, using the standard Win32 `SetThreadExecutionState` API.

Why this exists: if the whole system suspends (sleep/hibernate), EVERY
process is paused at the hardware level - CPU, network, timers, all of it.
There is no way for a Python/Qt app to "keep working through" an actual
system sleep; the only real option is to ask Windows not to go there in the
first place while the app needs to keep controlling the lamps.

This only blocks *automatic, idle-timeout* sleep - it does not override an
explicit user action (Start menu -> Sleep, closing a laptop lid per its own
power-plan setting), which is the correct, expected behavior for this API
(the same one video players and similar "keep the PC awake" apps use).

The display is deliberately still allowed to turn off / the session to lock
(ES_DISPLAY_REQUIRED is NOT set) - only full system suspend is prevented,
since a sleeping display doesn't stop the app from controlling lamps.
"""
from __future__ import annotations

import logging
import sys

logger = logging.getLogger("airam_lights.keep_awake")

_ES_CONTINUOUS = 0x80000000
_ES_SYSTEM_REQUIRED = 0x00000001


def prevent_sleep() -> bool:
    """Call once at startup. Returns True if the hold was applied (always
    False on non-Windows platforms, or if the Win32 call itself fails)."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        result = ctypes.windll.kernel32.SetThreadExecutionState(_ES_CONTINUOUS | _ES_SYSTEM_REQUIRED)
        if result == 0:
            logger.warning("SetThreadExecutionState returned failure - the PC may still auto-sleep")
            return False
        logger.info("System auto-sleep prevented while this app is running (display can still turn off)")
        return True
    except Exception:
        logger.exception("Could not call SetThreadExecutionState - the PC may still auto-sleep")
        return False


def allow_sleep() -> None:
    """Call once on shutdown to release the hold, restoring normal
    Windows power-management behavior."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.kernel32.SetThreadExecutionState(_ES_CONTINUOUS)
    except Exception:
        logger.exception("Could not release the sleep-prevention hold")
