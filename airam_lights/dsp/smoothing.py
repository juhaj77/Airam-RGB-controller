"""Attack/release exponential smoothing.

This is the core building block that makes the visualizer feel continuous
instead of the stock Airam Music Sync's abrupt, discrete color jumps: a
rising value can be tracked quickly (attack) while a falling value decays
more slowly (release), and every step moves only a fraction of the way to
the target rather than jumping straight to it.
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np


def _alpha_for(time_constant_ms: float, dt_s: float) -> float:
    """Convert a time constant (ms) + elapsed time (s) into an exponential
    smoothing coefficient alpha, s.t. value += (target - value) * alpha.

    alpha = 1 - exp(-dt / tau). tau <= 0 means "no smoothing" (alpha = 1).
    """
    tau_s = max(time_constant_ms, 0.0) / 1000.0
    if tau_s <= 1e-6 or dt_s <= 0:
        return 1.0
    return 1.0 - math.exp(-dt_s / tau_s)


class AttackReleaseSmoother:
    """Smooths a single scalar value with independent attack/release speeds."""

    def __init__(self, attack_ms: float = 60.0, release_ms: float = 300.0, initial: float = 0.0):
        self.attack_ms = attack_ms
        self.release_ms = release_ms
        self.value = initial
        self._last_time: Optional[float] = None

    def reset(self, value: float = 0.0) -> None:
        self.value = value
        self._last_time = None

    def update(self, target: float, dt_s: float) -> float:
        rising = target >= self.value
        tau_ms = self.attack_ms if rising else self.release_ms
        alpha = _alpha_for(tau_ms, dt_s)
        self.value += (target - self.value) * alpha
        return self.value


class HueSmoother:
    """Attack/release smoothing for a value that wraps at 360 degrees (hue),
    always taking the shortest angular path toward the target - a plain
    AttackReleaseSmoother would cut across the wrong way whenever the target
    crosses the 0/360 boundary (e.g. jumping from hue 350 to hue 10 should
    move +20, not -340).

    Used by "Beat Sync" mode: the target hue only changes on a detected beat,
    so in practice this just snaps quickly (via `time_constant_ms`) to each
    new target and then holds still until the next beat.
    """

    def __init__(self, time_constant_ms: float = 50.0, initial: float = 0.0):
        self.time_constant_ms = time_constant_ms
        self.value = initial % 360.0

    def reset(self, value: float = 0.0) -> None:
        self.value = value % 360.0

    def update(self, target_deg: float, dt_s: float) -> float:
        target = target_deg % 360.0
        delta = ((target - self.value + 180.0) % 360.0) - 180.0
        alpha = _alpha_for(self.time_constant_ms, dt_s)
        self.value = (self.value + delta * alpha) % 360.0
        return self.value


class MultiSmoother:
    """Vectorized attack/release smoothing for an array of independent
    channels (e.g. one per frequency band or one per lamp)."""

    def __init__(self, size: int, attack_ms: float = 60.0, release_ms: float = 300.0):
        self.size = size
        self.attack_ms = attack_ms
        self.release_ms = release_ms
        self.values = np.zeros(size, dtype=np.float64)

    def reset(self, values: Optional[np.ndarray] = None) -> None:
        self.values = np.zeros(self.size) if values is None else np.array(values, dtype=np.float64)

    def update(self, targets: np.ndarray, dt_s: float) -> np.ndarray:
        targets = np.asarray(targets, dtype=np.float64)
        rising = targets >= self.values
        alpha_rise = _alpha_for(self.attack_ms, dt_s)
        alpha_fall = _alpha_for(self.release_ms, dt_s)
        alphas = np.where(rising, alpha_rise, alpha_fall)
        self.values = self.values + (targets - self.values) * alphas
        return self.values
