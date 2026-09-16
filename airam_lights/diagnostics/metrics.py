"""Lightweight runtime metrics: event rates and latency stats.

Used by the diagnostics tab to show FFT update rate, visual update rate,
lamp command rate, and per-lamp latency, without pulling in a full metrics
library.
"""
from __future__ import annotations

import collections
import time
from typing import Deque, Optional


class RateCounter:
    """Tracks how many times `tick()` was called per second, over a sliding window."""

    def __init__(self, window_size: int = 100):
        self._times: Deque[float] = collections.deque(maxlen=window_size)

    def tick(self) -> None:
        self._times.append(time.perf_counter())

    def rate_hz(self) -> float:
        if len(self._times) < 2:
            return 0.0
        span = self._times[-1] - self._times[0]
        return (len(self._times) - 1) / span if span > 0 else 0.0


class LatencyStats:
    """Rolling min/avg/max latency (ms) over the last N samples."""

    def __init__(self, window_size: int = 50):
        self._samples: Deque[float] = collections.deque(maxlen=window_size)

    def add(self, latency_ms: float) -> None:
        self._samples.append(latency_ms)

    def last(self) -> Optional[float]:
        return self._samples[-1] if self._samples else None

    def avg(self) -> Optional[float]:
        return sum(self._samples) / len(self._samples) if self._samples else None

    def min(self) -> Optional[float]:
        return min(self._samples) if self._samples else None

    def max(self) -> Optional[float]:
        return max(self._samples) if self._samples else None
