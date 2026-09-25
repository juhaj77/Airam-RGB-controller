"""Verifies LampWorker's failure handling:

- the exponential backoff timer is actually engaged on failure (a past bug
  left it frozen, so a failing lamp retried at the engine's full push rate
  instead of backing off - see _on_send_failure's comment in manager.py).
- a device whose WHITE work_mode command fails over and over (seen in
  practice: some physical bulbs' status() response never lets tinytuya
  determine their DP value ranges, a per-device hardware/firmware
  difference, not a transient blip) gives up after a bounded number of
  consecutive failures instead of retrying/warning forever.
- a device that keeps failing at ANYTHING (RGB colour included, not just
  white) - e.g. a bulb whose persistent socket silently died - gets its
  tinytuya connection rebuilt automatically instead of retrying forever
  over a socket that's never coming back on its own (previously the only
  fix was physically power-cycling the bulb).

No real tinytuya device or network socket involved - LampDevice is replaced
with a minimal fake exposing just the methods LampWorker calls.
"""
from types import SimpleNamespace

from airam_lights.color.models import Color, WhiteTarget
from airam_lights.config.schema import NetworkConfig
import time

from airam_lights.lamps.manager import (
    _RECONNECT_THRESHOLD,
    _WHITE_RETRY_COOLDOWN_S,
    _WHITE_UNSUPPORTED_THRESHOLD,
    LampWorker,
)
from airam_lights.lamps.tuya_device import LampStatus


class _AlwaysFailsWhiteDevice:
    """Stands in for LampDevice: ensure_white_mode() no-ops (matches the
    real one's own internal try/except), set_white() always raises."""

    def __init__(self):
        self.config = SimpleNamespace(name="Fake", ip="10.0.0.1")
        self.status = LampStatus()
        self.reconnect_calls = 0

    def ensure_white_mode(self) -> None:
        pass

    def ensure_colour_mode(self) -> None:
        pass

    def set_white(self, brightness_percent, temp_percent, wait_for_ack=False):
        raise RuntimeError("colourtemp: Bulb not configured, cannot determine value ranges.")

    def set_color(self, r, g, b, wait_for_ack=False):
        return 5.0

    def reconnect(self) -> None:
        self.reconnect_calls += 1


class _DeadConnectionDevice:
    """Everything fails - RGB colour included - like a persistent socket
    that's silently died. reconnect() flips a flag that makes subsequent
    sends succeed again, simulating a fresh connection recovering it."""

    def __init__(self):
        self.config = SimpleNamespace(name="Fake", ip="10.0.0.1")
        self.status = LampStatus()
        self.reconnect_calls = 0
        self._alive = False

    def ensure_white_mode(self) -> None:
        pass

    def ensure_colour_mode(self) -> None:
        pass

    def set_white(self, brightness_percent, temp_percent, wait_for_ack=False):
        if not self._alive:
            raise ConnectionError("socket is not connected")
        return 5.0

    def set_color(self, r, g, b, wait_for_ack=False):
        if not self._alive:
            raise ConnectionError("socket is not connected")
        return 5.0

    def reconnect(self) -> None:
        self.reconnect_calls += 1
        self._alive = True


def _make_worker(device) -> LampWorker:
    # thread never started (.run() is never invoked) - _send_white() is
    # called directly, so this is plain synchronous unit testing.
    return LampWorker(device, NetworkConfig(), min_change_threshold=0.01)


def test_white_failure_updates_last_send_time_for_backoff():
    worker = _make_worker(_AlwaysFailsWhiteDevice())
    before = worker._last_send_time
    worker._send_white(WhiteTarget(brightness=1.0, temp=1.0))
    assert worker._last_send_time > before, "a failed send must still stamp _last_send_time so backoff engages"
    assert worker._consecutive_failures == 1


def test_gives_up_on_white_after_threshold_consecutive_failures():
    worker = _make_worker(_AlwaysFailsWhiteDevice())
    for i in range(_WHITE_UNSUPPORTED_THRESHOLD - 1):
        worker._send_white(WhiteTarget(brightness=1.0, temp=1.0))
        assert worker._white_unsupported is False, f"must not give up before the threshold (attempt {i + 1})"

    worker._send_white(WhiteTarget(brightness=1.0, temp=1.0))
    assert worker._white_unsupported is True
    assert worker._consecutive_white_failures == _WHITE_UNSUPPORTED_THRESHOLD
    # A cooldown, not a permanent ban - must be scheduled roughly
    # _WHITE_RETRY_COOLDOWN_S out from right now.
    remaining = worker._white_retry_after - time.perf_counter()
    assert 0 < remaining <= _WHITE_RETRY_COOLDOWN_S


def test_white_unsupported_is_a_cooldown_not_a_permanent_ban():
    """Regression test: giving up on white used to be permanent for the rest
    of the run. In practice, on a long session, EVERY lamp occasionally has
    a transient white-send hiccup (Wi-Fi jitter, a brief contention window)
    even though RGB colour keeps succeeding fine (which resets the general
    failure counter, so the reconnect mechanism never kicks in to give it a
    fresh chance either) - over enough time, most/all lamps could eventually
    rack up 5-in-a-row bad luck and drop out of the white-pulse effect one
    by one, permanently, even though they're perfectly capable. A device
    must get an automatic retry once its cooldown elapses."""
    device = _AlwaysFailsWhiteDevice()
    worker = _make_worker(device)
    for _ in range(_WHITE_UNSUPPORTED_THRESHOLD):
        worker._send_white(WhiteTarget(brightness=1.0, temp=1.0))
    assert worker._white_unsupported is True

    # Simulate the cooldown having elapsed (this is exactly what run()'s own
    # guard checks before ever calling _send_white again).
    worker._white_retry_after = time.perf_counter() - 1.0

    # The transient issue is gone now - this retry succeeds.
    device.set_white = lambda brightness_percent, temp_percent, wait_for_ack=False: 5.0
    worker._send_white(WhiteTarget(brightness=1.0, temp=1.0))
    assert worker._white_unsupported is False
    assert worker._consecutive_white_failures == 0


def test_a_successful_white_send_resets_the_failure_streak():
    device = _AlwaysFailsWhiteDevice()
    worker = _make_worker(device)
    for _ in range(_WHITE_UNSUPPORTED_THRESHOLD - 1):
        worker._send_white(WhiteTarget(brightness=1.0, temp=1.0))
    assert worker._white_unsupported is False

    # A one-off success (e.g. a transient network blip cleared up) must
    # reset the streak, so a device isn't permanently given up on after a
    # handful of unlucky-but-recoverable failures.
    device.set_white = lambda brightness_percent, temp_percent, wait_for_ack=False: 5.0
    worker._send_white(WhiteTarget(brightness=1.0, temp=1.0))
    assert worker._consecutive_white_failures == 0
    assert worker._white_unsupported is False


def test_reconnects_after_threshold_consecutive_failures_of_any_kind():
    device = _DeadConnectionDevice()
    worker = _make_worker(device)

    # Alternate colour/white sends, like a real session would (RGB Beat
    # Sync most of the time, white during a pulse) - both fail identically
    # since the whole connection is "dead" here, not just one DP.
    for i in range(_RECONNECT_THRESHOLD - 1):
        if i % 2 == 0:
            worker._send_color(Color(0.5, 0.5, 0.5))
        else:
            worker._send_white(WhiteTarget(brightness=1.0, temp=1.0))
        assert device.reconnect_calls == 0, f"must not reconnect before the threshold (attempt {i + 1})"

    worker._send_color(Color(0.5, 0.5, 0.5))
    assert device.reconnect_calls == 1
    assert worker._consecutive_failures == 0
    assert worker._colour_mode_ensured is False
    assert worker._white_mode_ensured is False

    # The rebuilt connection ("power-cycle equivalent") must actually get
    # used right away - the next send succeeds since _DeadConnectionDevice
    # flips alive on reconnect(), proving the worker doesn't stay wedged.
    worker._send_color(Color(0.5, 0.5, 0.5))
    assert worker._consecutive_failures == 0
    assert worker.stats.commands_sent == 1


def test_reconnect_also_gives_white_a_fresh_chance():
    device = _DeadConnectionDevice()
    worker = _make_worker(device)
    worker._white_unsupported = True
    worker._consecutive_white_failures = _WHITE_UNSUPPORTED_THRESHOLD

    for _ in range(_RECONNECT_THRESHOLD):
        worker._send_color(Color(0.5, 0.5, 0.5))

    assert device.reconnect_calls == 1
    assert worker._white_unsupported is False
    assert worker._consecutive_white_failures == 0
