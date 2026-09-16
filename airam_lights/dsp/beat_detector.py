"""Simple energy-based beat/onset detector.

This is the classic "sound-to-light" algorithm: compare the current energy
sample against a rolling short-term average of recent samples, and flag a
beat whenever the current value spikes well above that average. It is
intentionally simple (no ML, no tempo tracking) - it reacts directly to
transients (kick drums, snare hits, strong percussive attacks) which is
exactly what a music-reactive light needs, and it is cheap enough to run
every visual-engine tick.

Pure, dependency-free, and stateful only on its own small history buffer -
independent of audio capture, FFT, color mapping, and lamps, so it can be
unit-tested with a synthetic pulse train (see tests/test_beat_detector.py).
"""
from __future__ import annotations

import collections
from typing import Deque, Optional, Tuple


class BeatDetector:
    def __init__(
        self,
        history_seconds: float = 1.2,
        sensitivity: float = 1.6,
        min_interval_ms: float = 120.0,
        min_energy: float = 0.12,
        tempo_window: int = 8,
    ):
        """
        history_seconds: how far back the rolling average looks.
        sensitivity: a beat fires when energy > rolling_average * sensitivity.
                     Lower = more triggers (more sensitive), higher = fewer.
        min_interval_ms: refractory period - the minimum time between two
                     detected beats, so a single hit doesn't retrigger many
                     times while its energy is still elevated.
        min_energy: absolute floor - energy below this never triggers a beat,
                     even if it is a spike relative to a very quiet average
                     (avoids false triggers during near-silence).
        tempo_window: how many recent beat timestamps to keep for
                     `average_interval_s()` - used to estimate a rough tempo
                     without needing any music-theory concepts (e.g. the
                     Chase overlay's "sync to beat" speed).
        """
        self.sensitivity = sensitivity
        self.min_interval_ms = min_interval_ms
        self.min_energy = min_energy
        self.history_seconds = history_seconds
        self._history: Deque[Tuple[float, float]] = collections.deque()
        self._last_beat_time: Optional[float] = None
        self._beat_times: Deque[float] = collections.deque(maxlen=tempo_window)

    def reset(self) -> None:
        self._history.clear()
        self._last_beat_time = None
        self._beat_times.clear()

    def average_interval_s(self) -> Optional[float]:
        """Mean time between the most recent detected beats, in seconds, or
        None if fewer than 2 beats have been observed yet. This is a rough
        tempo estimate, not real BPM detection - good enough to drive a
        chase-light speed without needing to understand musical tempo."""
        if len(self._beat_times) < 2:
            return None
        times = list(self._beat_times)
        diffs = [t2 - t1 for t1, t2 in zip(times, times[1:])]
        return sum(diffs) / len(diffs)

    def update(self, energy: float, now_s: float) -> bool:
        """Feed one new energy sample (expected roughly 0..1). Returns True
        on the frame a new beat is detected, False otherwise."""
        self._history.append((now_s, energy))
        cutoff = now_s - self.history_seconds
        while self._history and self._history[0][0] < cutoff:
            self._history.popleft()

        if len(self._history) < 4:
            return False

        avg = sum(e for _, e in self._history) / len(self._history)
        since_last = (now_s - self._last_beat_time) * 1000.0 if self._last_beat_time is not None else None

        is_beat = (
            energy >= self.min_energy
            and energy > avg * self.sensitivity
            and (since_last is None or since_last >= self.min_interval_ms)
        )
        if is_beat:
            self._last_beat_time = now_s
            self._beat_times.append(now_s)
        return is_beat
