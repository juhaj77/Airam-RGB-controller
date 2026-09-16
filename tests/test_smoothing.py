"""Unit tests for attack/release smoothing - verifies the "no crude discrete
jumps" requirement: values move gradually and monotonically toward a new
target, with attack and release speeds independently configurable."""
import numpy as np

from airam_lights.dsp.smoothing import AttackReleaseSmoother, MultiSmoother


def test_smoother_moves_gradually_not_instantly():
    smoother = AttackReleaseSmoother(attack_ms=100.0, release_ms=100.0, initial=0.0)
    values = [smoother.update(1.0, dt_s=0.01) for _ in range(5)]
    # Should be rising, but never jump straight to the target in one small step.
    assert all(0.0 < v < 1.0 for v in values[:-1])
    assert values == sorted(values)


def test_smoother_eventually_converges_to_target():
    smoother = AttackReleaseSmoother(attack_ms=50.0, release_ms=50.0, initial=0.0)
    for _ in range(500):
        value = smoother.update(0.8, dt_s=0.01)
    assert abs(value - 0.8) < 0.01


def test_attack_and_release_speeds_differ():
    fast_attack = AttackReleaseSmoother(attack_ms=10.0, release_ms=1000.0, initial=0.0)
    slow_attack = AttackReleaseSmoother(attack_ms=1000.0, release_ms=10.0, initial=0.0)

    fast_rise = fast_attack.update(1.0, dt_s=0.02)
    slow_rise = slow_attack.update(1.0, dt_s=0.02)
    assert fast_rise > slow_rise  # fast attack reaches further in the same dt

    fast_attack.value = 1.0
    slow_attack.value = 1.0
    fast_fall = fast_attack.update(0.0, dt_s=0.02)  # now falling -> uses slow release
    slow_fall = slow_attack.update(0.0, dt_s=0.02)  # now falling -> uses fast release
    assert slow_fall < fast_fall  # slow_attack has the fast release here


def test_multismoother_tracks_independent_channels():
    smoother = MultiSmoother(size=3, attack_ms=30.0, release_ms=30.0)
    targets = np.array([0.1, 0.5, 0.9])
    for _ in range(200):
        values = smoother.update(targets, dt_s=0.01)
    assert np.allclose(values, targets, atol=0.02)
