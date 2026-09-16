"""Unit tests for the Ambient Scenes animator (effects/ambient.py) - the
manual control app's synchronized, self-looping animations."""
from airam_lights.color.models import Color, WhiteTarget
from airam_lights.config.schema import AmbientSceneConfig
from airam_lights.effects.ambient import AmbientAnimator


def test_zero_phase_offset_lamps_are_perfectly_synchronized():
    cfg = AmbientSceneConfig(scene="color_cycle", speed_hz=0.1, saturation=1.0, brightness=1.0)
    animator = AmbientAnimator(cfg)
    animator.tick(dt=2.5)  # advance to some arbitrary phase

    color_a = animator.compute_for_lamp(phase_offset_ms=0.0)
    color_b = animator.compute_for_lamp(phase_offset_ms=0.0)
    assert color_a == color_b  # identical inputs -> identical output, every time


def test_nonzero_phase_offset_produces_different_color():
    cfg = AmbientSceneConfig(scene="color_cycle", speed_hz=0.5, saturation=1.0, brightness=1.0)
    animator = AmbientAnimator(cfg)
    animator.tick(dt=1.0)

    synced = animator.compute_for_lamp(phase_offset_ms=0.0)
    shifted = animator.compute_for_lamp(phase_offset_ms=500.0)  # quarter-cycle at speed_hz=0.5
    assert synced != shifted


def test_color_cycle_sweeps_full_hue_wheel_over_one_period():
    cfg = AmbientSceneConfig(scene="color_cycle", speed_hz=1.0, saturation=1.0, brightness=1.0)
    animator = AmbientAnimator(cfg)

    hues = []
    for _ in range(4):
        animator.tick(dt=0.25)  # 4 steps of a 1-second period -> quarter-cycle each
        h, s, v = animator.compute_for_lamp().to_hsv()
        hues.append(h)

    assert abs(hues[0] - 90.0) < 1.0
    assert abs(hues[1] - 180.0) < 1.0
    assert abs(hues[2] - 270.0) < 1.0
    assert abs(hues[3] - 0.0) < 1.0  # wrapped back around


def test_breathing_oscillates_between_min_and_max_brightness():
    cfg = AmbientSceneConfig(scene="breathing", speed_hz=1.0, hue=0.0, saturation=0.0, brightness=0.9, min_brightness=0.1)
    animator = AmbientAnimator(cfg)

    values = []
    for _ in range(4):
        animator.tick(dt=0.25)
        _, _, v = animator.compute_for_lamp().to_hsv()
        values.append(v)

    assert min(values) >= 0.09  # never below the trough
    assert max(values) <= 0.91  # never above the peak
    assert max(values) - min(values) > 0.5  # actually oscillates, not flat


def test_breathing_output_is_rgb_color():
    cfg = AmbientSceneConfig(scene="breathing")
    animator = AmbientAnimator(cfg)
    assert animator.output_kind() == "rgb"
    assert isinstance(animator.compute_for_lamp(), Color)


def test_temp_breathing_output_is_white_target_and_oscillates():
    cfg = AmbientSceneConfig(scene="temp_breathing", speed_hz=1.0, brightness=0.7, temp_min=0.0, temp_max=1.0)
    animator = AmbientAnimator(cfg)
    assert animator.output_kind() == "white"

    temps = []
    for _ in range(4):
        animator.tick(dt=0.25)
        target = animator.compute_for_lamp()
        assert isinstance(target, WhiteTarget)
        assert abs(target.brightness - 0.7) < 1e-6  # brightness stays fixed for temp_breathing
        temps.append(target.temp)

    assert min(temps) < 0.2
    assert max(temps) > 0.8


def test_reset_returns_phase_to_zero():
    cfg = AmbientSceneConfig(speed_hz=1.0)
    animator = AmbientAnimator(cfg)
    animator.tick(dt=0.5)
    assert animator.phase != 0.0
    animator.reset()
    assert animator.phase == 0.0


def test_reverse_flips_color_cycle_direction():
    forward = AmbientAnimator(AmbientSceneConfig(scene="color_cycle", speed_hz=1.0, reverse=False))
    backward = AmbientAnimator(AmbientSceneConfig(scene="color_cycle", speed_hz=1.0, reverse=True))

    forward.tick(dt=0.1)
    backward.tick(dt=0.1)

    assert forward.phase > 0.0
    assert abs(backward.phase - (1.0 - forward.phase)) < 1e-9

    h_forward, _, _ = forward.compute_for_lamp().to_hsv()
    h_backward, _, _ = backward.compute_for_lamp().to_hsv()
    assert h_forward != h_backward
