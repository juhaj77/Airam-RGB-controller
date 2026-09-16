"""Self-looping ambient animations, driven by one shared PC-side clock.

Every selected lamp reads the SAME phase value on every tick, so they are
synchronized by construction - no more power-cycling a smart plug and a
light switch at the same moment and hoping the timing lines up. See
config.schema.AmbientSceneConfig for the full rationale (short version: the
bulb's own onboard 'scene' animations each run on their own internal clock
from whenever they were individually triggered, which is exactly why they
can't be synchronized externally).
"""
from __future__ import annotations

import math
from typing import Union

from ..color.models import Color, WhiteTarget, lerp
from ..config.schema import AmbientSceneConfig

# Which physical work_mode each scene drives - the caller uses this to know
# whether to push_colors() (RGB) or push_white_targets() (WHITE) for a lamp.
SCENE_OUTPUT_KIND = {
    "color_cycle": "rgb",
    "breathing": "rgb",
    "temp_breathing": "white",
}


def _pulse01(phase: float) -> float:
    """A smooth 0..1 pulse (starts and ends at 0, peaks at phase=0.5) - one
    full 'breath' per phase cycle 0..1."""
    return (math.sin(phase * 2.0 * math.pi - math.pi / 2.0) + 1.0) / 2.0


class AmbientAnimator:
    def __init__(self, config: AmbientSceneConfig):
        self.config = config
        self.phase = 0.0  # 0..1, one full animation cycle

    def update_config(self, config: AmbientSceneConfig) -> None:
        self.config = config

    def reset(self) -> None:
        self.phase = 0.0

    def tick(self, dt: float) -> None:
        direction = -1.0 if self.config.reverse else 1.0
        self.phase = (self.phase + direction * self.config.speed_hz * dt) % 1.0

    def output_kind(self) -> str:
        return SCENE_OUTPUT_KIND.get(self.config.scene, "rgb")

    def compute_for_lamp(self, phase_offset_ms: float = 0.0) -> Union[Color, WhiteTarget]:
        """phase_offset_ms: this lamp's PerLampEffect.phase_offset_ms - 0
        (the default) means perfectly synchronized with every other lamp;
        nonzero values shift this lamp's position in the cycle, creating a
        traveling "wave" look instead."""
        cfg = self.config
        offset_cycles = (phase_offset_ms / 1000.0) * cfg.speed_hz
        local_phase = (self.phase - offset_cycles) % 1.0

        if cfg.scene == "temp_breathing":
            t = _pulse01(local_phase)
            temp = lerp(cfg.temp_min, cfg.temp_max, t)
            return WhiteTarget(brightness=cfg.brightness, temp=temp).clamped()

        if cfg.scene == "breathing":
            value = lerp(cfg.min_brightness, cfg.brightness, _pulse01(local_phase))
            return Color.from_hsv(cfg.hue, cfg.saturation, value)

        # "color_cycle" (default): hue itself sweeps the full wheel every cycle.
        hue = local_phase * 360.0
        return Color.from_hsv(hue, cfg.saturation, cfg.brightness)
