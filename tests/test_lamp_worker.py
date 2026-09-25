"""Verifies LampWorker's white-mode failure handling:

- the exponential backoff timer is actually engaged on failure (a past bug
  left it frozen, so a failing lamp retried at the engine's full push rate
  instead of backing off - see _on_send_failure's comment in manager.py).
- a device whose WHITE work_mode command fails over and over (seen in
  practice: some physical bulbs' status() response never lets tinytuya
  determine their DP value ranges, a per-device hardware/firmware
  difference, not a transient blip) gives up after a bounded number of
  consecutive failures instead of retrying/warning forever.

No real tinytuya device or network socket involved - LampDevice is replaced
with a minimal fake exposing just the methods LampWorker calls.
"""
from types import SimpleNamespace

from airam_lights.color.models import WhiteTarget
from airam_lights.config.schema import NetworkConfig
from airam_lights.lamps.manager import _WHITE_UNSUPPORTED_THRESHOLD, LampWorker
from airam_lights.lamps.tuya_device import LampStatus


class _AlwaysFailsWhiteDevice:
    """Stands in for LampDevice: ensure_white_mode() no-ops (matches the
    real one's own internal try/except), set_white() always raises."""

    def __init__(self):
        self.config = SimpleNamespace(name="Fake", ip="10.0.0.1")
        self.status = LampStatus()

    def ensure_white_mode(self) -> None:
        pass

    def ensure_colour_mode(self) -> None:
        pass

    def set_white(self, brightness_percent, temp_percent, wait_for_ack=False):
        raise RuntimeError("colourtemp: Bulb not configured, cannot determine value ranges.")

    def set_color(self, r, g, b, wait_for_ack=False):
        return 5.0


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
