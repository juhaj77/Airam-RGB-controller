"""Unit tests for the DSP layer - runs entirely on synthetic signals, no
audio hardware or lamps needed."""
import numpy as np

from airam_lights.dsp.bands import band_energy, spectral_centroid_hz
from airam_lights.dsp.fft_engine import FFTEngine


def _sine(freq_hz: float, samplerate: int, n: int, amplitude: float = 0.5) -> np.ndarray:
    t = np.arange(n) / samplerate
    return (amplitude * np.sin(2 * np.pi * freq_hz * t)).astype(np.float32)


def test_fft_peak_at_correct_frequency():
    samplerate = 48000
    fft_size = 2048
    signal = _sine(1000.0, samplerate, fft_size)
    engine = FFTEngine(samplerate, fft_size)
    frame = engine.compute(signal)
    peak_freq = frame.freqs[np.argmax(frame.magnitude)]
    assert abs(peak_freq - 1000.0) < (samplerate / fft_size) * 2


def test_band_energy_responds_to_signal_in_band():
    samplerate = 48000
    fft_size = 2048
    engine = FFTEngine(samplerate, fft_size)

    silence = np.zeros(fft_size, dtype=np.float32)
    bass_tone = _sine(80.0, samplerate, fft_size)

    silent_frame = engine.compute(silence)
    bass_frame = engine.compute(bass_tone)

    silent_level = band_energy(silent_frame, 20, 150)
    bass_level = band_energy(bass_frame, 20, 150)

    assert bass_level > silent_level
    assert 0.0 <= silent_level <= 1.0
    assert 0.0 <= bass_level <= 1.0


def test_band_energy_is_monotonic_with_amplitude():
    samplerate = 48000
    fft_size = 2048
    engine = FFTEngine(samplerate, fft_size)

    quiet = engine.compute(_sine(1000.0, samplerate, fft_size, amplitude=0.05))
    loud = engine.compute(_sine(1000.0, samplerate, fft_size, amplitude=0.5))

    assert band_energy(loud, 150, 2000) > band_energy(quiet, 150, 2000)


def test_spectral_centroid_tracks_dominant_frequency():
    samplerate = 48000
    fft_size = 2048
    engine = FFTEngine(samplerate, fft_size)

    low = engine.compute(_sine(100.0, samplerate, fft_size))
    high = engine.compute(_sine(8000.0, samplerate, fft_size))

    assert spectral_centroid_hz(low) < spectral_centroid_hz(high)
