"""Frequency-band energy extraction and spectral feature helpers.

Pure numpy functions operating on a SpectrumFrame - no state, easy to test
and to reuse for both the coarse "N configurable bands" mode and the finer
features (spectral centroid/contrast) used by HSV mode.
"""
from __future__ import annotations

from typing import Sequence

import numpy as np

from .fft_engine import SpectrumFrame

_EPS = 1e-9


def band_energy(frame: SpectrumFrame, low_hz: float, high_hz: float, floor_db: float = -90.0) -> float:
    """Return a normalized 0..1 energy level for one frequency band.

    Uses average magnitude in dB across the band's bins, rescaled from
    [floor_db, 0] to [0, 1]. Using dB (rather than raw linear power) gives a
    perceptually-reasonable, much less "bass-dominated" response than
    summing linear power directly, and matches how humans judge loudness
    across the spectrum.
    """
    mask = (frame.freqs >= low_hz) & (frame.freqs < high_hz)
    if not np.any(mask):
        return 0.0
    db = frame.magnitude_db[mask]
    avg_db = float(np.mean(db))
    level = (avg_db - floor_db) / (0.0 - floor_db)
    return float(np.clip(level, 0.0, 1.0))


def band_energies(frame: SpectrumFrame, bands: Sequence, floor_db: float = -90.0) -> list:
    """bands: sequence of objects with .low_hz / .high_hz (e.g. BandDefinition)."""
    return [band_energy(frame, b.low_hz, b.high_hz, floor_db) for b in bands]


def spectral_centroid_hz(frame: SpectrumFrame, low_hz: float = 20.0, high_hz: float = 16000.0) -> float:
    """Energy-weighted average frequency within [low_hz, high_hz] - used to
    drive hue in HSV mode ("frequency distribution controls hue")."""
    mask = (frame.freqs >= low_hz) & (frame.freqs <= high_hz)
    if not np.any(mask):
        return low_hz
    freqs = frame.freqs[mask]
    weights = np.maximum(frame.magnitude[mask], 0.0)
    total = float(np.sum(weights))
    if total < _EPS:
        return low_hz
    return float(np.sum(freqs * weights) / total)


def spectral_contrast(frame: SpectrumFrame, low_hz: float = 20.0, high_hz: float = 16000.0) -> float:
    """0..1 measure of how "peaky" vs. "flat" the spectrum is, used to drive
    saturation in HSV mode ("spectral contrast controls saturation").

    Computed as (peak - mean) / (peak + eps) over magnitude in dB, so silence
    and pure white noise both read as low contrast, while a strong isolated
    tone/kick reads as high contrast.
    """
    mask = (frame.freqs >= low_hz) & (frame.freqs <= high_hz)
    if not np.any(mask):
        return 0.0
    db = frame.magnitude_db[mask]
    peak = float(np.max(db))
    mean = float(np.mean(db))
    span = peak - frame_floor(frame)
    if span <= _EPS:
        return 0.0
    contrast = (peak - mean) / span
    return float(np.clip(contrast * 2.0, 0.0, 1.0))


def frame_floor(frame: SpectrumFrame) -> float:
    return float(np.min(frame.magnitude_db))
