"""Local (LAN) control of a single Airam/Tuya bulb via tinytuya.

IMPORTANT (see DEVICE_NOTES.md): this module never hardcodes datapoint IDs.
All colour/brightness/power control goes through `tinytuya.BulbDevice`, which
reads the device's own `status()` response and adapts to whichever DP layout
(type A/B/C) the physical bulb actually reports. `refresh_status()` also
stores the *raw* dps dictionary so the diagnostics UI can show you exactly
what the bulb sent back, instead of trusting an assumption blindly.

All methods here are blocking (tinytuya is a synchronous socket library).
Callers must run them off the UI thread - see `lamps/manager.py`, which runs
one worker thread per lamp for exactly this reason.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from ..config.schema import DeviceConfig

logger = logging.getLogger("airam_lights.lamps")


@dataclass
class LampStatus:
    online: bool = False
    raw_dps: dict = field(default_factory=dict)
    bulb_type: Optional[str] = None
    last_latency_ms: Optional[float] = None
    last_error: Optional[str] = None
    last_updated: Optional[float] = None


class LampDevice:
    """Thin, defensive wrapper around tinytuya.BulbDevice for one physical bulb."""

    def __init__(self, config: DeviceConfig):
        self.config = config
        self.status = LampStatus()
        self._bulb = None
        self._connect_error: Optional[str] = None
        self._build()

    def _build(self) -> None:
        try:
            import tinytuya
        except ImportError as e:
            self._connect_error = "tinytuya is not installed (pip install tinytuya)"
            logger.error(self._connect_error)
            return
        try:
            # tinytuya expects `version` as a float (e.g. 3.3, not "3.3"). Passing a
            # string here silently breaks its internal protocol-version comparisons,
            # which shows up as status()/set_colour() failing even with a correct
            # local_key - confirmed while testing against real Airam bulbs.
            self._bulb = tinytuya.BulbDevice(
                dev_id=self.config.id,
                address=self.config.ip,
                local_key=self.config.local_key,
                version=float(self.config.version),
            )
            self._bulb.set_socketPersistent(True)
            self._bulb.set_socketTimeout(2.0)
        except Exception as e:
            self._connect_error = f"Failed to initialize device object: {e}"
            logger.exception("Error creating tinytuya.BulbDevice for %s", self.config.name)

    def reconfigure(self, config: DeviceConfig) -> None:
        """Called when the user edits IP/local_key/version for this device."""
        self.config = config
        self._build()

    # -- read ---------------------------------------------------------------

    def refresh_status(self) -> LampStatus:
        """Blocking. Queries the bulb's current state and updates self.status.

        Raises the underlying exception after recording it in self.status, so
        callers running this in a background thread/executor can log it, and
        the diagnostics page can also read the human-readable last_error.
        """
        if self._bulb is None:
            self.status = LampStatus(online=False, last_error=self._connect_error or "device not initialized")
            return self.status

        t0 = time.perf_counter()
        try:
            result = self._bulb.status()
            latency_ms = (time.perf_counter() - t0) * 1000.0

            if isinstance(result, dict) and "dps" in result:
                self.status = LampStatus(
                    online=True,
                    raw_dps=dict(result["dps"]),
                    bulb_type=getattr(self._bulb, "bulb_type", None),
                    last_latency_ms=latency_ms,
                    last_error=None,
                    last_updated=time.time(),
                )
            elif isinstance(result, dict) and result.get("Error"):
                self.status = LampStatus(
                    online=False,
                    last_error=str(result.get("Error")),
                    last_latency_ms=latency_ms,
                    last_updated=time.time(),
                )
            else:
                self.status = LampStatus(
                    online=False,
                    last_error=f"Unexpected response shape: {result!r}",
                    last_latency_ms=latency_ms,
                    last_updated=time.time(),
                )
            return self.status
        except Exception as e:
            self.status = LampStatus(online=False, last_error=str(e), last_updated=time.time())
            logger.warning("status() failed for '%s' (%s): %s", self.config.name, self.config.ip, e)
            raise

    # -- write ----------------------------------------------------------------

    def ensure_colour_mode(self) -> None:
        """Some Tuya bulbs ignore colour DPs unless work_mode is set to
        'colour' first. Safe/cheap to call once after connecting."""
        if self._bulb is None:
            return
        try:
            self._bulb.set_mode("colour")
        except Exception:
            logger.debug("set_mode('colour') not supported/failed for %s (may be fine)", self.config.name)

    def set_color(self, r: int, g: int, b: int, wait_for_ack: bool = False) -> float:
        """r,g,b in 0..255. Returns latency in ms. Raises on failure."""
        if self._bulb is None:
            raise RuntimeError(self._connect_error or "device not initialized")
        t0 = time.perf_counter()
        self._bulb.set_colour(r, g, b, nowait=not wait_for_ack)
        latency_ms = (time.perf_counter() - t0) * 1000.0
        self.status.last_latency_ms = latency_ms
        self.status.online = True
        self.status.last_error = None
        return latency_ms

    def set_brightness_percent(self, percent: float, wait_for_ack: bool = False) -> float:
        if self._bulb is None:
            raise RuntimeError(self._connect_error or "device not initialized")
        t0 = time.perf_counter()
        self._bulb.set_brightness_percentage(max(0, min(100, round(percent))), nowait=not wait_for_ack)
        latency_ms = (time.perf_counter() - t0) * 1000.0
        self.status.last_latency_ms = latency_ms
        return latency_ms

    def ensure_white_mode(self) -> None:
        """Counterpart to ensure_colour_mode() - switches work_mode (DP 21)
        to 'white' so DP 22 (bright_value_v2) and DP 23 (temp_value_v2) take
        effect instead of the RGB colour DP. Safe/cheap to call once."""
        if self._bulb is None:
            return
        try:
            self._bulb.set_mode("white")
        except Exception:
            logger.debug("set_mode('white') not supported/failed for %s (may be fine)", self.config.name)

    def set_white(self, brightness_percent: float, temp_percent: float, wait_for_ack: bool = False) -> float:
        """brightness_percent, temp_percent in 0..100 (temp: 0=warmest,
        100=coolest). Uses tinytuya's own percentage-based colourtemp/
        brightness setters (documented BulbDevice methods) rather than
        writing raw DP values, consistent with how set_color() above goes
        through tinytuya's set_colour() instead of a hand-rolled DP 24
        payload - see DEVICE_NOTES.md for what's confirmed vs. assumed about
        this specific call combination on the Airam bulbs.

        NOT YET independently confirmed against the physical bulbs (unlike
        set_color(), which was verified via tools/phase1_test.py) - run a
        manual white-balance test before relying on this for anything
        important, and update DEVICE_NOTES.md with the result."""
        if self._bulb is None:
            raise RuntimeError(self._connect_error or "device not initialized")
        t0 = time.perf_counter()
        self._bulb.set_colourtemp_percentage(max(0, min(100, round(temp_percent))), nowait=not wait_for_ack)
        self._bulb.set_brightness_percentage(max(0, min(100, round(brightness_percent))), nowait=not wait_for_ack)
        latency_ms = (time.perf_counter() - t0) * 1000.0
        self.status.last_latency_ms = latency_ms
        self.status.online = True
        self.status.last_error = None
        return latency_ms

    def turn_on(self, wait_for_ack: bool = False) -> None:
        if self._bulb is None:
            raise RuntimeError(self._connect_error or "device not initialized")
        self._bulb.turn_on(nowait=not wait_for_ack)

    def turn_off(self, wait_for_ack: bool = False) -> None:
        if self._bulb is None:
            raise RuntimeError(self._connect_error or "device not initialized")
        self._bulb.turn_off(nowait=not wait_for_ack)
