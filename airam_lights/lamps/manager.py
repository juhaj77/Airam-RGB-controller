"""Multi-lamp manager: one independent worker thread per lamp.

Design notes (see README.md "Network / performance"):

- Each lamp gets its own daemon thread with a single-slot "latest target"
  mailbox (not a queue) - if several color updates arrive before the worker
  gets to send, only the *latest* is ever sent. This is exactly the coalescing
  behavior the spec asks for: never build a backlog, never spam the bulb.
- Each worker independently rate-limits itself to `lamp_command_rate_hz` and
  skips sends whose color barely changed (`min_change_threshold`), so a lamp
  that's essentially steady stops generating network traffic even though the
  visual engine is still running at its own (usually higher) update rate.
- A failing/slow lamp only affects its own thread - it can never block or
  slow down the other 7 lamps, or the UI.
- This uses plain `threading`, not asyncio: tinytuya is a blocking socket
  library, and mixing asyncio with PySide6's event loop adds real complexity
  for no benefit here, since each lamp already gets full concurrency via its
  own OS thread.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

from ..color.models import Color, WhiteTarget
from ..config.schema import DeviceConfig, NetworkConfig
from .discovery import DiscoveredDevice, scan_network
from .tuya_device import LampDevice

logger = logging.getLogger("airam_lights.lamps")


@dataclass
class WorkerStats:
    commands_sent: int = 0
    commands_skipped_unchanged: int = 0
    commands_failed: int = 0
    last_send_time: Optional[float] = None


class LampWorker(threading.Thread):
    def __init__(self, device: LampDevice, network_cfg: NetworkConfig, min_change_threshold: float):
        super().__init__(daemon=True, name=f"lamp-worker-{device.config.name}")
        self.device = device
        self.network_cfg = network_cfg
        self.min_change_threshold = min_change_threshold
        self.stats = WorkerStats()

        # Exactly one of these two is live at a time - setting one clears the
        # other, so a lamp switching between RGB and White modes never sends
        # a stale target from the mode it just left.
        self._target_color: Optional[Color] = None
        self._target_white: Optional[WhiteTarget] = None
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._last_sent_color: Optional[Color] = None
        self._last_sent_white: Optional[WhiteTarget] = None
        self._last_send_time = 0.0
        self._consecutive_failures = 0
        self._colour_mode_ensured = False
        self._white_mode_ensured = False

    def set_target(self, color: Color) -> None:
        with self._lock:
            self._target_color = color
            self._target_white = None
        self._wake.set()

    def set_white_target(self, target: WhiteTarget) -> None:
        with self._lock:
            self._target_white = target
            self._target_color = None
        self._wake.set()

    def update_network_config(self, network_cfg: NetworkConfig, min_change_threshold: float) -> None:
        self.network_cfg = network_cfg
        self.min_change_threshold = min_change_threshold

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def _effective_interval(self) -> float:
        base = 1.0 / max(self.network_cfg.lamp_command_rate_hz, 0.1)
        if self.network_cfg.auto_backoff and self._consecutive_failures > 0:
            # Simple capped exponential backoff: 2x, 4x, 8x ... up to 16x the
            # configured interval, so a lamp that's offline doesn't get hammered.
            backoff = min(2 ** self._consecutive_failures, 16)
            return base * backoff
        return base

    def run(self) -> None:
        while not self._stop.is_set():
            got_signal = self._wake.wait(timeout=0.5)
            if self._stop.is_set():
                break
            if not got_signal:
                continue
            self._wake.clear()

            with self._lock:
                color, white = self._target_color, self._target_white

            if color is None and white is None:
                continue

            interval = self._effective_interval()
            elapsed = time.perf_counter() - self._last_send_time
            if elapsed < interval:
                time.sleep(interval - elapsed)
                # Newer targets may have arrived while we slept - use them.
                with self._lock:
                    color, white = self._target_color, self._target_white

            if white is not None:
                if self._last_sent_white is not None and white.distance(self._last_sent_white) < self.min_change_threshold:
                    self.stats.commands_skipped_unchanged += 1
                    continue
                self._send_white(white)
            elif color is not None:
                if self._last_sent_color is not None and color.distance(self._last_sent_color) < self.min_change_threshold:
                    self.stats.commands_skipped_unchanged += 1
                    continue
                self._send_color(color)

    def _on_send_success(self) -> None:
        self._last_send_time = time.perf_counter()
        self.stats.commands_sent += 1
        self.stats.last_send_time = self._last_send_time
        self._consecutive_failures = 0
        self.device.status.online = True
        self.device.status.last_error = None

    def _on_send_failure(self, e: Exception) -> None:
        self.stats.commands_failed += 1
        self._consecutive_failures += 1
        self.device.status.online = False
        self.device.status.last_error = str(e)
        logger.warning("Failed to send to '%s' (%s): %s", self.device.config.name, self.device.config.ip, e)

    def _send_color(self, color: Color) -> None:
        try:
            if not self._colour_mode_ensured:
                self.device.ensure_colour_mode()
                self._colour_mode_ensured = True
                self._white_mode_ensured = False
            r, g, b = color.to_rgb255()
            self.device.set_color(r, g, b, wait_for_ack=False)
            self._last_sent_color = color
            self._last_sent_white = None
            self._on_send_success()
        except Exception as e:
            self._on_send_failure(e)

    def _send_white(self, target: WhiteTarget) -> None:
        try:
            if not self._white_mode_ensured:
                self.device.ensure_white_mode()
                self._white_mode_ensured = True
                self._colour_mode_ensured = False
            self.device.set_white(target.brightness * 100.0, target.temp * 100.0, wait_for_ack=False)
            self._last_sent_white = target
            self._last_sent_color = None
            self._on_send_success()
        except Exception as e:
            self._on_send_failure(e)


class LampManager:
    """Owns all configured lamps and their worker threads."""

    def __init__(self, network_cfg: NetworkConfig, min_change_threshold: float = 0.015):
        self.network_cfg = network_cfg
        self.min_change_threshold = min_change_threshold
        self.devices: Dict[str, LampDevice] = {}
        self.workers: Dict[str, LampWorker] = {}

    # -- configuration ---------------------------------------------------------

    def load_devices(self, device_configs: List[DeviceConfig]) -> None:
        for dc in device_configs:
            self.add_device(dc)

    def add_device(self, dc: DeviceConfig) -> LampDevice:
        if dc.id in self.devices:
            self.remove_device(dc.id)
        dev = LampDevice(dc)
        worker = LampWorker(dev, self.network_cfg, self.min_change_threshold)
        worker.start()
        self.devices[dc.id] = dev
        self.workers[dc.id] = worker
        logger.info("Added lamp '%s' (%s, id=%s)", dc.name, dc.ip, dc.id)
        return dev

    def remove_device(self, device_id: str) -> None:
        worker = self.workers.pop(device_id, None)
        if worker:
            worker.stop()
        self.devices.pop(device_id, None)

    def update_device_config(self, dc: DeviceConfig) -> None:
        dev = self.devices.get(dc.id)
        if dev is None:
            self.add_device(dc)
            return
        dev.reconfigure(dc)

    def set_network_config(self, network_cfg: NetworkConfig, min_change_threshold: float) -> None:
        self.network_cfg = network_cfg
        self.min_change_threshold = min_change_threshold
        for w in self.workers.values():
            w.update_network_config(network_cfg, min_change_threshold)

    # -- selection ---------------------------------------------------------------

    def selected_device_ids(self) -> List[str]:
        return [d.config.id for d in self.devices.values() if d.config.enabled and d.config.selected]

    def set_selected(self, device_id: str, selected: bool) -> None:
        dev = self.devices.get(device_id)
        if dev:
            dev.config.selected = selected

    def select_all(self) -> None:
        for dev in self.devices.values():
            dev.config.selected = True

    def clear_selection(self) -> None:
        for dev in self.devices.values():
            dev.config.selected = False

    def apply_group(self, group_device_ids: List[str]) -> None:
        group_set = set(group_device_ids)
        for dev in self.devices.values():
            dev.config.selected = dev.config.id in group_set

    # -- runtime -------------------------------------------------------------------

    def push_colors(self, colors: Dict[str, Color]) -> None:
        """Send one target RGB color per device id (work_mode='colour').
        Called at the configured visual_update_hz from the engine - each
        worker independently decides whether/when to actually transmit it."""
        for device_id, color in colors.items():
            worker = self.workers.get(device_id)
            if worker is not None:
                worker.set_target(color)

    def push_white_targets(self, targets: Dict[str, WhiteTarget]) -> None:
        """Same as push_colors(), but for the bulb's WHITE work_mode
        (brightness + color temperature) - e.g. the Beat Sync White mode."""
        for device_id, target in targets.items():
            worker = self.workers.get(device_id)
            if worker is not None:
                worker.set_white_target(target)

    def refresh_all_status(self, executor) -> None:
        """Submits a status() refresh for every device to the given
        concurrent.futures executor so slow/offline lamps don't block others."""
        for dev in self.devices.values():
            executor.submit(self._safe_refresh, dev)

    @staticmethod
    def _safe_refresh(dev: LampDevice) -> None:
        try:
            dev.refresh_status()
        except Exception:
            pass  # already recorded on dev.status by refresh_status()

    def discover(self, timeout: float = 8.0) -> List[DiscoveredDevice]:
        return scan_network(timeout)

    def shutdown(self) -> None:
        for worker in self.workers.values():
            worker.stop()
        for worker in self.workers.values():
            worker.join(timeout=1.0)
