"""Shared 'Chase / Rotating Light' overlay.

This is used by BOTH the audio-reactive VisualizationEngine (engine/) and the
standalone, no-audio manual control app (ui/manual_controller.py) - one
implementation, so a fix or feature here (like lamp-position grouping)
benefits both places at once instead of drifting apart.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence

from ..color.models import Color, WhiteTarget, circular_lerp_deg, clip, lerp
from ..config.schema import ChaseEffectConfig, PerLampEffect, WhiteChaseEffectConfig
from ..dsp.beat_detector import BeatDetector


def _smoothstep(t: float) -> float:
    """The standard 'ease in/out' S-curve (t*t*(3-2t)) - flat (near-zero
    slope) at both t=0 and t=1, fastest change in between. Equivalent to a
    symmetric cubic Bezier ease, which is what users usually mean by
    "Bezier curve" for this kind of transition."""
    t = clip(t)
    return t * t * (3.0 - 2.0 * t)


def _falloff_weight(dist: float, width: float, curve: str) -> float:
    """0..1 highlight weight at a given distance (in chase positions) from
    the nearest rotator. 'linear' falls off at a constant rate, so the peak
    (dist=0) is a single fleeting instant. 'bezier' dwells near the peak
    (and near zero) for longer, transitioning fastest in the middle -
    directly addresses "the highlight color flies by too quickly"."""
    linear_weight = clip(1.0 - dist / max(width, 1e-6))
    if curve == "bezier":
        return _smoothstep(linear_weight)
    return linear_weight


def _swept_min_distance(target: float, start: float, end: float, n: float) -> float:
    """Minimum circular distance (topology of size n) from `target` to the
    whole continuous arc swept from `start` to `end` during one tick - not
    just to `end` (the position's value after the tick).

    At high rotation speeds, a single tick can move the highlight all the
    way past a lamp's position between one sample and the next, so sampling
    only the end-of-tick position means that lamp's dist never reaches 0 and
    it never sees its full target color - the highlight "jumps over" it.
    Using the whole swept arc means a lamp the highlight crossed during the
    tick still registers dist=0 (its true peak), regardless of speed."""
    if n <= 0:
        return 0.0
    lo, hi = (start, end) if start <= end else (end, start)
    span = hi - lo
    if span >= n:
        return 0.0  # swept a full lap or more this tick: every position was covered
    k_lo = int(math.floor((lo - target) / n)) - 1
    k_hi = int(math.ceil((hi - target) / n)) + 1
    best = float("inf")
    for k in range(k_lo, k_hi + 1):
        candidate = target + k * n
        if lo <= candidate <= hi:
            return 0.0
        best = min(best, abs(candidate - lo), abs(candidate - hi))
    return best


def _local_dwell_weight(position: float, n: int, dwell_weights: Optional[Sequence[float]]) -> float:
    """The dwell weight of whichever chase position `position` currently
    sits nearest to, clamped away from zero. Returns 1.0 (uniform) if no
    weights were given."""
    if not dwell_weights:
        return 1.0
    idx = int(round(position)) % n
    if idx >= len(dwell_weights):
        return 1.0
    return max(dwell_weights[idx], 0.05)


def get_chase_groups(per_lamp_effects: Dict[str, PerLampEffect], selected_ids: Sequence[str]) -> List[List[str]]:
    """Groups the given lamps by their PerLampEffect.chase_order, ascending.

    Lamps that share the same order number end up in the same group and
    always animate together as one "position" - this is what makes the
    chase work for physical layouts that aren't a single ring (e.g. two
    lamps on each of four walls: give each wall's pair the same order
    number, and the chase treats the whole wall as one step).

    Lamps with no chase_order set (None) are excluded entirely.
    """
    buckets: Dict[int, List[str]] = {}
    for device_id in selected_ids:
        effect = per_lamp_effects.get(device_id)
        if effect is not None and effect.chase_order is not None:
            buckets.setdefault(effect.chase_order, []).append(device_id)
    return [buckets[key] for key in sorted(buckets.keys())]


def get_chase_group_dwell_weights(
    per_lamp_effects: Dict[str, PerLampEffect], groups: List[List[str]]
) -> List[float]:
    """Per-position dwell-time multiplier, in the same order as `groups`
    (from `get_chase_groups`). A group's weight is the average of its
    members' `PerLampEffect.chase_dwell_mult` - normally every lamp sharing
    a physical fixture is set to the same value. Higher = the moving
    highlight lingers there longer; lower = it passes through faster.
    Missing lamps/effects default to 1.0 (uniform dwell, matching the
    original behavior before this setting existed)."""
    weights: List[float] = []
    for group in groups:
        mults = [
            per_lamp_effects[device_id].chase_dwell_mult
            for device_id in group
            if device_id in per_lamp_effects
        ]
        weights.append(sum(mults) / len(mults) if mults else 1.0)
    return weights


class ChaseAnimator:
    """Owns the chase's moving position(s) and renders them onto a color
    dict. Stateful (the position persists between calls) but otherwise
    independent of audio, lamps, or UI - easy to unit test and to drive from
    either a music-reactive tick or a plain timer."""

    def __init__(self, config: ChaseEffectConfig):
        self.config = config
        self._position = 0.0
        self._sweep_start = 0.0
        self._sweep_end = 0.0
        self._beat_detector = BeatDetector(
            sensitivity=config.beat_sensitivity,
            min_interval_ms=config.beat_min_interval_ms,
            min_energy=config.beat_min_energy,
        )

    @property
    def position(self) -> float:
        return self._position

    @position.setter
    def position(self, value: float) -> None:
        """Directly placing the rotator (e.g. tests pinning it to an exact
        spot, bypassing tick()) collapses to a zero-length sweep right there
        - a "teleport", not a move - so `apply()` samples only that spot,
        matching the pre-sweep-tracking behavior. `tick()` is the only path
        that produces a genuine swept arc; it writes `_position` directly to
        bypass this collapse."""
        self._position = value
        self._sweep_start = value
        self._sweep_end = value

    def update_config(self, config: ChaseEffectConfig) -> None:
        self.config = config
        self._beat_detector.sensitivity = config.beat_sensitivity
        self._beat_detector.min_interval_ms = config.beat_min_interval_ms
        self._beat_detector.min_energy = config.beat_min_energy

    def reset(self) -> None:
        self.position = 0.0
        self._beat_detector.reset()

    def tick(
        self,
        dt: float,
        num_positions: int,
        beat_band_energy: Optional[float] = None,
        now_s: Optional[float] = None,
        dwell_weights: Optional[Sequence[float]] = None,
    ) -> None:
        """Advances the chase position. `num_positions` is the current
        number of distinct chase groups (from `get_chase_groups`) - it can
        change over time as lamps are added/removed from the chase without
        breaking anything.

        `beat_band_energy` + `now_s`: pass these (from the caller's own band
        energy extraction) to enable `sync_to_beat`. Omit them (as the
        no-audio manual app does) and the chase always falls back to its
        constant `speed_rotations_per_s`, even if `sync_to_beat` is set in
        the shared config - it simply has no beat signal to sync to.

        `dwell_weights`: optional per-position dwell-time multipliers (see
        `get_chase_group_dwell_weights`), same length/order as `groups`.
        The position's advance rate is locally divided by the weight of
        whichever position it is currently nearest to, so a weight of 2.0
        makes the highlight spend roughly twice as long around that
        position; 1.0 (or omitting this entirely) reproduces the original,
        perfectly uniform dwell time.
        """
        cfg = self.config
        n = max(1, num_positions)
        direction = -1.0 if cfg.reverse else 1.0

        if cfg.sync_to_beat and beat_band_energy is not None and now_s is not None:
            self._beat_detector.update(beat_band_energy, now_s)
            interval = self._beat_detector.average_interval_s()
            steps_per_s = (cfg.beat_multiplier / interval) if interval and interval > 0.02 else cfg.speed_rotations_per_s * n
        else:
            steps_per_s = cfg.speed_rotations_per_s * n

        local_dwell = _local_dwell_weight(self._position, n, dwell_weights)
        delta = direction * steps_per_s * dt / local_dwell
        self._sweep_start = self._position
        self._sweep_end = self._position + delta
        self._position = self._sweep_end % n  # bypass the setter: keep the sweep just computed

    def apply(self, colors: Dict[str, Color], groups: List[List[str]]) -> Dict[str, Color]:
        """Renders the current position onto `colors`, returning a new dict.
        Brightness is always a multiplicative boost on each lamp's own
        current value - never an independent/fixed brightness - so a lamp
        the active mode has deliberately driven to black (e.g. a Beat Sync
        dark pulse) stays black no matter the chase's intensity or width."""
        n = len(groups)
        if n < 2:
            return colors

        cfg = self.config
        num_rotators = max(1, int(cfg.num_rotators))
        spacing = n / num_rotators
        rotator_sweeps = [
            (self._sweep_start + k * spacing, self._sweep_end + k * spacing) for k in range(num_rotators)
        ]

        result = dict(colors)
        for i, group in enumerate(groups):
            weight = 0.0
            for start, end in rotator_sweeps:
                dist = _swept_min_distance(float(i), start, end, n)
                w = _falloff_weight(dist, cfg.width, cfg.falloff_curve)
                if w > weight:
                    weight = w
            if weight <= 0.0:
                continue

            for device_id in group:
                base_color = result.get(device_id, Color.black())
                h_base, s_base, v_base = base_color.to_hsv()

                if cfg.color_mode == "complementary":
                    target_hue = (h_base + 180.0) % 360.0
                    target_sat = s_base
                elif cfg.color_mode == "hue_shift":
                    # Each position shows a progressively different hue, so
                    # the traveling light's own color gradually shifts
                    # through the spectrum as it moves around the loop.
                    target_hue = (cfg.custom_hue_deg + i * cfg.hue_shift_step_deg) % 360.0
                    target_sat = cfg.custom_saturation
                else:  # "custom"
                    target_hue = cfg.custom_hue_deg
                    target_sat = cfg.custom_saturation

                h_out = circular_lerp_deg(h_base, target_hue, weight)
                s_out = lerp(s_base, target_sat, weight)
                v_out = clip(v_base * (1.0 + weight * cfg.intensity))

                result[device_id] = Color.from_hsv(h_out, s_out, v_out)
        return result


class WhiteChaseAnimator:
    """The White-mode counterpart to ChaseAnimator: instead of an RGB/hue
    highlight, a warm-or-cool color TEMPERATURE region rotates through the
    chase-ordered lamp positions. No beat-sync here (see
    WhiteChaseEffectConfig) - built for the standalone manual control app,
    which has no audio input.

    Brightness is, exactly like ChaseAnimator, a multiplicative boost on
    each lamp's own current brightness - a lamp at 0 stays at 0."""

    def __init__(self, config: WhiteChaseEffectConfig):
        self.config = config
        self._position = 0.0
        self._sweep_start = 0.0
        self._sweep_end = 0.0

    @property
    def position(self) -> float:
        return self._position

    @position.setter
    def position(self, value: float) -> None:
        """See ChaseAnimator.position setter: a direct assignment "teleports"
        (zero-length sweep at that spot); only tick() produces a real swept
        arc, writing `_position` directly to bypass this collapse."""
        self._position = value
        self._sweep_start = value
        self._sweep_end = value

    def update_config(self, config: WhiteChaseEffectConfig) -> None:
        self.config = config

    def reset(self) -> None:
        self.position = 0.0

    def tick(self, dt: float, num_positions: int, dwell_weights: Optional[Sequence[float]] = None) -> None:
        cfg = self.config
        n = max(1, num_positions)
        direction = -1.0 if cfg.reverse else 1.0
        steps_per_s = cfg.speed_rotations_per_s * n
        local_dwell = _local_dwell_weight(self._position, n, dwell_weights)
        delta = direction * steps_per_s * dt / local_dwell
        self._sweep_start = self._position
        self._sweep_end = self._position + delta
        self._position = self._sweep_end % n  # bypass the setter: keep the sweep just computed

    def apply(self, targets: Dict[str, WhiteTarget], groups: List[List[str]]) -> Dict[str, WhiteTarget]:
        n = len(groups)
        if n < 2:
            return targets

        cfg = self.config
        num_rotators = max(1, int(cfg.num_rotators))
        spacing = n / num_rotators
        rotator_sweeps = [
            (self._sweep_start + k * spacing, self._sweep_end + k * spacing) for k in range(num_rotators)
        ]

        result = dict(targets)
        for i, group in enumerate(groups):
            weight = 0.0
            for start, end in rotator_sweeps:
                dist = _swept_min_distance(float(i), start, end, n)
                w = _falloff_weight(dist, cfg.width, cfg.falloff_curve)
                if w > weight:
                    weight = w
            if weight <= 0.0:
                continue

            for device_id in group:
                base = result.get(device_id, WhiteTarget(0.0, 0.5))
                temp_out = lerp(base.temp, cfg.target_temp, weight)
                bright_out = clip(base.brightness * (1.0 + weight * cfg.intensity))
                result[device_id] = WhiteTarget(brightness=bright_out, temp=temp_out)
        return result
