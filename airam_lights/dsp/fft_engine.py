"""Real-time FFT spectrum computation.

Independent of any lamp/network code by design (see README.md architecture
section) - this module only ever deals with numpy arrays in and out, so it
can be unit-tested and reused with fake/synthetic audio.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class SpectrumFrame:
    freqs: np.ndarray  # Hz, ascending
    magnitude: np.ndarray  # linear magnitude, same length as freqs
    magnitude_db: np.ndarray  # 20*log10(magnitude), floor-clamped


class FFTEngine:
    """Windowed FFT with a persistent Hann window and frequency axis.

    fft_size should generally be >= block_size for good frequency resolution
    at low frequencies (e.g. 2048 samples @ 48 kHz -> ~23 Hz/bin, enough to
    resolve the default 20-60 Hz bottom band).
    """

    def __init__(self, samplerate: int, fft_size: int = 2048, floor_db: float = -90.0):
        self.samplerate = samplerate
        self.fft_size = fft_size
        self.floor_db = floor_db
        self._window = np.hanning(fft_size).astype(np.float32)
        self._window_gain = float(np.sum(self._window))
        self.freqs = np.fft.rfftfreq(fft_size, d=1.0 / samplerate)

    def set_samplerate(self, samplerate: int) -> None:
        if samplerate == self.samplerate:
            return
        self.samplerate = samplerate
        self.freqs = np.fft.rfftfreq(self.fft_size, d=1.0 / samplerate)

    def compute(self, samples: np.ndarray) -> SpectrumFrame:
        """samples: mono float32 array, length >= fft_size (extra is ignored,
        the last fft_size samples are used - i.e. caller should pass the most
        recent window)."""
        if len(samples) < self.fft_size:
            padded = np.zeros(self.fft_size, dtype=np.float32)
            padded[-len(samples):] = samples
            samples = padded
        else:
            samples = samples[-self.fft_size:]

        windowed = samples * self._window
        spectrum = np.fft.rfft(windowed)
        magnitude = np.abs(spectrum) / max(self._window_gain / 2.0, 1e-9)
        magnitude_db = 20.0 * np.log10(np.maximum(magnitude, 1e-9))
        magnitude_db = np.maximum(magnitude_db, self.floor_db)
        return SpectrumFrame(freqs=self.freqs, magnitude=magnitude, magnitude_db=magnitude_db)
