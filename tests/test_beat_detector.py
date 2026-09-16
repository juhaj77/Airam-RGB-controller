"""Unit tests for the beat/onset detector - synthetic energy signals only,
no audio hardware needed."""
from airam_lights.dsp.beat_detector import BeatDetector


def _feed(detector: BeatDetector, samples, dt=1.0 / 60.0):
    """samples: list of energy values, fed at a fixed dt starting at t=0.
    Returns the list of timestamps where a beat was detected."""
    beats = []
    t = 0.0
    for value in samples:
        if detector.update(value, t):
            beats.append(t)
        t += dt
    return beats


def test_detects_periodic_pulses():
    detector = BeatDetector(sensitivity=1.5, min_interval_ms=100.0, min_energy=0.1)
    # Quiet baseline with a sharp pulse every 0.5s (~30 frames at 60Hz).
    samples = []
    for i in range(300):
        samples.append(0.9 if i % 30 == 0 else 0.05)
    beats = _feed(detector, samples)
    # Should detect roughly one beat per pulse (10 pulses in 300 frames @30-frame period).
    assert 8 <= len(beats) <= 10


def test_refractory_period_prevents_double_triggers():
    detector = BeatDetector(sensitivity=1.2, min_interval_ms=200.0, min_energy=0.1)
    # A sustained loud burst for several consecutive frames should only ever
    # fire once within the refractory window, not once per frame.
    samples = [0.05] * 10 + [0.9] * 10 + [0.05] * 10
    beats = _feed(detector, samples, dt=1.0 / 60.0)
    assert len(beats) == 1


def test_average_interval_tracks_periodic_pulses():
    detector = BeatDetector(sensitivity=1.5, min_interval_ms=100.0, min_energy=0.1)
    samples = []
    for i in range(300):
        samples.append(0.9 if i % 30 == 0 else 0.05)  # a pulse every 30 frames @ 60Hz = 0.5s
    assert detector.average_interval_s() is None  # nothing observed yet
    _feed(detector, samples)
    avg = detector.average_interval_s()
    assert avg is not None
    assert abs(avg - 0.5) < 0.05


def test_quiet_signal_never_triggers():
    detector = BeatDetector(sensitivity=1.5, min_interval_ms=100.0, min_energy=0.2)
    samples = [0.05] * 200  # flat and below min_energy
    beats = _feed(detector, samples)
    assert beats == []


def test_consecutive_beats_always_respect_refractory_period():
    # A ratio-based detector like this one *will* keep firing throughout a
    # sustained rising swell (current is always above the trailing average on
    # a ramp) - that's expected/acceptable for a party-light effect. The
    # actual invariant that must always hold is the refractory spacing.
    detector = BeatDetector(sensitivity=1.5, min_interval_ms=50.0, min_energy=0.05)
    samples = [min(0.9, 0.01 * i) for i in range(200)]
    beats = _feed(detector, samples)
    assert len(beats) > 3  # confirms the ramp does keep retriggering, as expected
    for t1, t2 in zip(beats, beats[1:]):
        assert (t2 - t1) * 1000.0 >= detector.min_interval_ms - 1e-9
