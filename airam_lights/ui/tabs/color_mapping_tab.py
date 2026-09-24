"""Color Mapping tab: full detail controls for RGB Frequency / Custom / HSV
Music modes, plus global response curve, smoothing, and presets."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ...config.schema import ChaseEffectConfig, ColorMappingConfig, RGBModeConfig
from ..controller import AppController
from ..widgets.channel_map_editor import ChannelMapEditor
from ..widgets.hue_slider import HueSlider
from ..widgets.param_slider import FloatSlider


class RGBModeEditor(QWidget):
    """Three ChannelMapEditors side by side (R/G/B) + overall sensitivity."""

    def __init__(self, cfg: RGBModeConfig, on_change, parent=None):
        super().__init__(parent)
        self._on_change = on_change
        layout = QVBoxLayout(self)

        row = QHBoxLayout()
        self.r_editor = ChannelMapEditor("R (default: Bass)", cfg.r)
        self.g_editor = ChannelMapEditor("G (default: Mid)", cfg.g)
        self.b_editor = ChannelMapEditor("B (default: Treble)", cfg.b)
        for e in (self.r_editor, self.g_editor, self.b_editor):
            e.changed.connect(self._emit)
            row.addWidget(e)
        layout.addLayout(row)

        self.sensitivity_slider = FloatSlider("Sensitivity", 0.1, 4.0, cfg.sensitivity)
        self.sensitivity_slider.valueChanged.connect(self._emit)
        layout.addWidget(self.sensitivity_slider)

    def _emit(self, *_args) -> None:
        self._on_change(self.to_config())

    def to_config(self) -> RGBModeConfig:
        return RGBModeConfig(
            r=self.r_editor.to_channel_map(),
            g=self.g_editor.to_channel_map(),
            b=self.b_editor.to_channel_map(),
            sensitivity=self.sensitivity_slider.value(),
        )


class ColorMappingTab(QWidget):
    def __init__(self, controller: AppController, parent=None):
        super().__init__(parent)
        self.controller = controller
        cm = controller.config.color_mapping

        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)
        inner = QWidget()
        scroll.setWidget(inner)
        root = QVBoxLayout(inner)

        sub_tabs = QTabWidget()
        root.addWidget(sub_tabs)

        # -- RGB Frequency mode -----------------------------------------------------
        self.rgb_editor = RGBModeEditor(cm.rgb, self._on_rgb_changed)
        sub_tabs.addTab(self.rgb_editor, "RGB Frequency")

        # -- Custom mode --------------------------------------------------------------
        self.custom_editor = RGBModeEditor(cm.custom, self._on_custom_changed)
        sub_tabs.addTab(self.custom_editor, "Custom")

        # -- HSV mode -------------------------------------------------------------------
        hsv_widget = QWidget()
        hsv_layout = QVBoxLayout(hsv_widget)
        hsv = cm.hsv
        self.hue_min_slider = HueSlider("Hue @ low freq", hsv.hue_min_deg)
        self.hue_max_slider = HueSlider("Hue @ high freq", hsv.hue_max_deg)
        self.bright_min_slider = FloatSlider("Brightness min", 0.0, 1.0, hsv.brightness_min)
        self.bright_max_slider = FloatSlider("Brightness max", 0.0, 1.0, hsv.brightness_max)
        self.sat_base_slider = FloatSlider("Saturation base", 0.0, 1.0, hsv.saturation_base)
        self.sat_contrast_slider = FloatSlider("Saturation from contrast", 0.0, 1.0, hsv.saturation_contrast_gain)
        self.hsv_sensitivity_slider = FloatSlider("Sensitivity", 0.1, 4.0, hsv.sensitivity)
        for w in (
            self.hue_min_slider,
            self.hue_max_slider,
            self.bright_min_slider,
            self.bright_max_slider,
            self.sat_base_slider,
            self.sat_contrast_slider,
            self.hsv_sensitivity_slider,
        ):
            w.valueChanged.connect(self._on_hsv_changed)
            hsv_layout.addWidget(w)
        hsv_desc_label = QLabel(
            "Hue follows the spectral centroid (frequency distribution), brightness "
            "follows overall energy, saturation follows spectral contrast (peaky vs. flat)."
        )
        hsv_desc_label.setWordWrap(True)
        hsv_layout.addWidget(hsv_desc_label)
        sub_tabs.addTab(hsv_widget, "HSV Music")

        # -- Beat Sync mode -----------------------------------------------------------
        beat_widget = QWidget()
        beat_layout = QVBoxLayout(beat_widget)
        bs = cm.beat_sync

        detect_row = QHBoxLayout()
        detect_row.addWidget(QLabel("Beat detection band:"))
        self.beat_low_spin = QSpinBox()
        self.beat_low_spin.setRange(20, 20000)
        self.beat_low_spin.setSuffix(" Hz")
        self.beat_low_spin.setValue(int(bs.detect_low_hz))
        self.beat_low_spin.setToolTip(
            "Which frequencies count as a 'beat' at all - every hue/brightness snap below, and both "
            "pulse types further down, only ever happen when a hit is detected somewhere in this range."
        )
        detect_row.addWidget(self.beat_low_spin)
        detect_row.addWidget(QLabel("-"))
        self.beat_high_spin = QSpinBox()
        self.beat_high_spin.setRange(20, 20000)
        self.beat_high_spin.setSuffix(" Hz")
        self.beat_high_spin.setValue(int(bs.detect_high_hz))
        self.beat_high_spin.setToolTip(self.beat_low_spin.toolTip())
        detect_row.addWidget(self.beat_high_spin)
        detect_row.addStretch(1)
        beat_layout.addLayout(detect_row)
        beat_band_note = QLabel(
            "Default 40-200 Hz targets kick drums; widen it (e.g. to also cover hi-hats/cymbals) if "
            "you want the white pulse below to have hits of its own to react to - see its note further "
            "down."
        )
        beat_band_note.setWordWrap(True)
        beat_layout.addWidget(beat_band_note)

        self.beat_sensitivity_slider = FloatSlider(
            "Sensitivity", 1.05, 4.0, bs.sensitivity, decimals=2,
            tooltip="Higher = only very sharp, obvious hits register as a beat at all, so every hue/"
            "brightness snap and both pulse types below fire less often but more confidently.",
        )
        self.beat_min_interval_slider = FloatSlider(
            "Min interval", 30.0, 1000.0, bs.min_interval_ms, decimals=0, suffix=" ms",
            tooltip="Minimum time between two triggered beats - stops one sustained hit from "
            "re-triggering the hue/brightness snap (and pulses) many times in quick succession.",
        )
        self.beat_min_energy_slider = FloatSlider(
            "Min energy floor", 0.0, 1.0, bs.min_energy,
            tooltip="Absolute loudness floor below which nothing can trigger, even if it's a relative "
            "spike - keeps quiet passages from firing hue/brightness snaps or pulses on near-silence.",
        )
        for w in (self.beat_sensitivity_slider, self.beat_min_interval_slider, self.beat_min_energy_slider):
            w.valueChanged.connect(self._on_beat_changed)
            beat_layout.addWidget(w)
        beat_sensitivity_note = QLabel("Lower sensitivity / higher min-interval = fewer, more confident beat triggers.")
        beat_sensitivity_note.setWordWrap(True)
        beat_layout.addWidget(beat_sensitivity_note)

        hue_row = QHBoxLayout()
        hue_row.addWidget(QLabel("Hue mode:"))
        self.beat_hue_mode_combo = QComboBox()
        self.beat_hue_mode_combo.addItems(["random", "step", "spectrum"])
        self.beat_hue_mode_combo.setCurrentText(bs.hue_mode)
        self.beat_hue_mode_combo.setToolTip(
            "Which hue (color, i.e. the RGB mix) each beat jumps to - see the note below for what each "
            "option does. Saturation and brightness are controlled separately by the sliders further down."
        )
        self.beat_hue_mode_combo.currentTextChanged.connect(self._on_beat_changed)
        hue_row.addWidget(self.beat_hue_mode_combo)
        hue_row.addStretch(1)
        beat_layout.addLayout(hue_row)
        beat_hue_mode_note = QLabel(
            "random: a fresh, sufficiently-different color every hit. step: cycles through the color "
            "wheel by a fixed angle each hit (never repeats for a long time). spectrum: hue follows "
            "the spectral centroid at the moment of the hit."
        )
        beat_hue_mode_note.setWordWrap(True)
        beat_layout.addWidget(beat_hue_mode_note)

        self.beat_hue_step_slider = FloatSlider(
            "Hue step (for 'step')", 1.0, 180.0, bs.hue_step_deg, decimals=1, suffix=" deg",
            tooltip="How far around the color wheel the hue jumps on each beat, in 'step' mode - "
            "bigger steps mean more visually different colors from one hit to the next.",
        )
        self.beat_min_jump_slider = FloatSlider(
            "Min hue jump (for 'random')", 0.0, 180.0, bs.min_hue_jump_deg, decimals=0, suffix=" deg",
            tooltip="In 'random' mode, how different the new hue must be from the last one - prevents "
            "two consecutive beats from landing on nearly the same color purely by chance.",
        )
        self.beat_saturation_slider = FloatSlider(
            "Saturation", 0.0, 1.0, bs.saturation,
            tooltip="The base color vividness on every beat (1.0 = fully saturated, lower = more "
            "pastel/washed out) - this is the saturation both the dark and white pulses below "
            "temporarily push away from, then ease back to.",
        )
        self.beat_flash_slider = FloatSlider(
            "Flash brightness", 0.0, 1.0, bs.flash_brightness,
            tooltip="How bright the color is exactly on the beat, before it starts decaying - this is "
            "the flash you actually see land on the hit itself.",
        )
        self.beat_sustain_slider = FloatSlider(
            "Sustain brightness", 0.0, 1.0, bs.sustain_brightness,
            tooltip="How bright it settles to between beats, once the flash has decayed - the resting/"
            "idle brightness the lamp sits at until the next hit.",
        )
        self.beat_hue_attack_slider = FloatSlider(
            "Hue snap speed", 5.0, 500.0, bs.hue_attack_ms, decimals=0, suffix=" ms",
            tooltip="How fast the color transitions to the new hue after a beat - low = an almost "
            "instant snap, high = a visible fade from the old color into the new one.",
        )
        self.beat_bright_attack_slider = FloatSlider(
            "Brightness attack", 1.0, 200.0, bs.brightness_attack_ms, decimals=0, suffix=" ms",
            tooltip="How fast brightness jumps up to Flash brightness on a beat - low = a sharp, "
            "percussive flash; high = brightness eases up instead of snapping.",
        )
        self.beat_bright_release_slider = FloatSlider(
            "Brightness decay", 50.0, 2000.0, bs.brightness_release_ms, decimals=0, suffix=" ms",
            tooltip="How slowly brightness fades from the flash back down to Sustain brightness - "
            "higher means a longer glow tail lingering after each hit.",
        )
        for w in (
            self.beat_hue_step_slider,
            self.beat_min_jump_slider,
            self.beat_saturation_slider,
            self.beat_flash_slider,
            self.beat_sustain_slider,
            self.beat_hue_attack_slider,
            self.beat_bright_attack_slider,
            self.beat_bright_release_slider,
        ):
            w.valueChanged.connect(self._on_beat_changed)
            beat_layout.addWidget(w)

        beat_dark_note = QLabel(
            "Dark pulses: on a random subset of beats, briefly dip brightness toward black BEFORE "
            "flashing - a rhythm-synced pause/strobe accent, on top of the hue and brightness above."
        )
        beat_dark_note.setWordWrap(True)
        beat_layout.addWidget(beat_dark_note)

        self.beat_dark_prob_slider = FloatSlider(
            "Dark pulse probability", 0.0, 1.0, bs.dark_pulse_probability, decimals=2,
            tooltip="Chance a given beat gets this dark dip instead of flashing immediately - "
            "0 = never, 1 = every beat.",
        )
        self.beat_dark_duration_slider = FloatSlider(
            "Dark pulse duration", 10.0, 500.0, bs.dark_pulse_duration_ms, decimals=0, suffix=" ms",
            tooltip="How long brightness is held down near black before the delayed flash actually happens.",
        )
        self.beat_dark_depth_slider = FloatSlider(
            "Dark pulse depth", 0.0, 1.0, bs.dark_pulse_depth, decimals=2,
            tooltip="How far toward black the dip goes - 1.0 = fully black for the duration above, "
            "lower = a partial dim instead of a total blackout.",
        )
        for w in (self.beat_dark_prob_slider, self.beat_dark_duration_slider, self.beat_dark_depth_slider):
            w.valueChanged.connect(self._on_beat_changed)
            beat_layout.addWidget(w)

        beat_white_pulse_note = QLabel(
            "White pulses: on a random subset of beats, briefly push saturation toward one extreme "
            "right as the flash happens - e.g. a hi-hat/cymbal accent snapping to near-white for an "
            "instant. Independent of dark pulses above - each rolls its own probability on every beat, "
            "so both, either, or neither can happen on any given hit."
        )
        beat_white_pulse_note.setWordWrap(True)
        beat_layout.addWidget(beat_white_pulse_note)

        self.beat_white_pulse_enabled_checkbox = QCheckBox("Enabled")
        self.beat_white_pulse_enabled_checkbox.setChecked(bs.white_pulse_enabled)
        self.beat_white_pulse_enabled_checkbox.setToolTip(
            "Turns the white/saturation-pulse accent on or off - leave unchecked if you never want "
            "this effect (dark pulses above are unaffected either way)."
        )
        self.beat_white_pulse_enabled_checkbox.toggled.connect(self._on_beat_changed)
        beat_layout.addWidget(self.beat_white_pulse_enabled_checkbox)

        self.beat_white_pulse_invert_checkbox = QCheckBox(
            "Invert (saturate toward full color instead of desaturating toward white)"
        )
        self.beat_white_pulse_invert_checkbox.setChecked(bs.white_pulse_invert)
        self.beat_white_pulse_invert_checkbox.setToolTip(
            "Off: the pulse desaturates the color toward white (saturation -> 0). On: it instead "
            "saturates toward a fully vivid color (saturation -> 1) - useful if the base Saturation "
            "above is already fairly pastel, where pulsing further toward white wouldn't read as an accent."
        )
        self.beat_white_pulse_invert_checkbox.toggled.connect(self._on_beat_changed)
        beat_layout.addWidget(self.beat_white_pulse_invert_checkbox)

        self.beat_white_pulse_prob_slider = FloatSlider(
            "White pulse probability", 0.0, 1.0, bs.white_pulse_probability, decimals=2,
            tooltip="Chance a given beat gets this saturation pulse - 0 = never, 1 = every beat.",
        )
        self.beat_white_pulse_duration_slider = FloatSlider(
            "White pulse duration", 10.0, 500.0, bs.white_pulse_duration_ms, decimals=0, suffix=" ms",
            tooltip="How long saturation is held at the extreme (white, or fully vivid if inverted) "
            "before it starts easing back to the base Saturation.",
        )
        self.beat_white_pulse_depth_slider = FloatSlider(
            "White pulse depth", 0.0, 1.0, bs.white_pulse_depth, decimals=2,
            tooltip="How far toward the extreme the pulse pushes saturation - 1.0 = all the way to "
            "white/fully vivid, lower = a partial push instead.",
        )
        self.beat_white_pulse_attack_slider = FloatSlider(
            "White pulse attack", 1.0, 300.0, bs.white_pulse_attack_ms, decimals=0, suffix=" ms",
            tooltip="How fast saturation snaps to the extreme when the pulse starts - low = an "
            "instant flash to white/vivid, right on the beat.",
        )
        self.beat_white_pulse_release_slider = FloatSlider(
            "White pulse release", 10.0, 1000.0, bs.white_pulse_release_ms, decimals=0, suffix=" ms",
            tooltip="How slowly saturation eases back to the base Saturation value once the pulse's "
            "duration ends - higher means a longer visible fade back to normal color.",
        )
        for w in (
            self.beat_white_pulse_prob_slider,
            self.beat_white_pulse_duration_slider,
            self.beat_white_pulse_depth_slider,
            self.beat_white_pulse_attack_slider,
            self.beat_white_pulse_release_slider,
        ):
            w.valueChanged.connect(self._on_beat_changed)
            beat_layout.addWidget(w)

        self.beat_low_spin.valueChanged.connect(self._on_beat_changed)
        self.beat_high_spin.valueChanged.connect(self._on_beat_changed)

        sub_tabs.addTab(beat_widget, "Beat Sync")

        # -- Beat Sync White mode -------------------------------------------------------
        bsw_widget = QWidget()
        bsw_layout = QVBoxLayout(bsw_widget)
        bsw = cm.beat_sync_white
        bsw_desc_label = QLabel(
            "Same rhythm-reactive envelope as Beat Sync, but drives the bulb's WHITE work_mode "
            "(brightness + color temperature) instead of RGB - warm/cool flashes on the beat. "
            "See DEVICE_NOTES.md: the underlying set_white() call is not yet independently "
            "confirmed against the physical bulbs the way RGB is."
        )
        bsw_desc_label.setWordWrap(True)
        bsw_layout.addWidget(bsw_desc_label)

        bsw_detect_row = QHBoxLayout()
        bsw_detect_row.addWidget(QLabel("Beat detection band:"))
        self.bsw_low_spin = QSpinBox()
        self.bsw_low_spin.setRange(20, 20000)
        self.bsw_low_spin.setSuffix(" Hz")
        self.bsw_low_spin.setValue(int(bsw.detect_low_hz))
        bsw_detect_row.addWidget(self.bsw_low_spin)
        bsw_detect_row.addWidget(QLabel("-"))
        self.bsw_high_spin = QSpinBox()
        self.bsw_high_spin.setRange(20, 20000)
        self.bsw_high_spin.setSuffix(" Hz")
        self.bsw_high_spin.setValue(int(bsw.detect_high_hz))
        bsw_detect_row.addWidget(self.bsw_high_spin)
        bsw_detect_row.addStretch(1)
        bsw_layout.addLayout(bsw_detect_row)

        self.bsw_sensitivity_slider = FloatSlider("Sensitivity", 1.05, 4.0, bsw.sensitivity, decimals=2)
        self.bsw_min_interval_slider = FloatSlider("Min interval", 30.0, 1000.0, bsw.min_interval_ms, decimals=0, suffix=" ms")
        self.bsw_min_energy_slider = FloatSlider("Min energy floor", 0.0, 1.0, bsw.min_energy)
        for w in (self.bsw_sensitivity_slider, self.bsw_min_interval_slider, self.bsw_min_energy_slider):
            w.valueChanged.connect(self._on_beat_white_changed)
            bsw_layout.addWidget(w)

        bsw_temp_mode_row = QHBoxLayout()
        bsw_temp_mode_row.addWidget(QLabel("Temperature mode:"))
        self.bsw_temp_mode_combo = QComboBox()
        self.bsw_temp_mode_combo.addItems(["random", "alternate"])
        self.bsw_temp_mode_combo.setCurrentText(bsw.temp_mode)
        self.bsw_temp_mode_combo.currentTextChanged.connect(self._on_beat_white_changed)
        bsw_temp_mode_row.addWidget(self.bsw_temp_mode_combo)
        bsw_temp_mode_row.addStretch(1)
        bsw_layout.addLayout(bsw_temp_mode_row)
        bsw_temp_mode_note = QLabel(
            "random: a new temperature every hit. alternate: ping-pongs between the warm and cool ends."
        )
        bsw_temp_mode_note.setWordWrap(True)
        bsw_layout.addWidget(bsw_temp_mode_note)

        self.bsw_temp_min_slider = FloatSlider("Temp range min (warm)", 0.0, 1.0, bsw.temp_min, decimals=2)
        self.bsw_temp_max_slider = FloatSlider("Temp range max (cool)", 0.0, 1.0, bsw.temp_max, decimals=2)
        self.bsw_min_jump_slider = FloatSlider("Min temp jump (for 'random')", 0.0, 1.0, bsw.min_temp_jump, decimals=2)
        self.bsw_flash_slider = FloatSlider("Flash brightness", 0.0, 1.0, bsw.flash_brightness)
        self.bsw_sustain_slider = FloatSlider("Sustain brightness", 0.0, 1.0, bsw.sustain_brightness)
        self.bsw_temp_attack_slider = FloatSlider("Temp snap speed", 5.0, 500.0, bsw.temp_attack_ms, decimals=0, suffix=" ms")
        self.bsw_bright_attack_slider = FloatSlider("Brightness attack", 1.0, 200.0, bsw.brightness_attack_ms, decimals=0, suffix=" ms")
        self.bsw_bright_release_slider = FloatSlider("Brightness decay", 50.0, 2000.0, bsw.brightness_release_ms, decimals=0, suffix=" ms")
        for w in (
            self.bsw_temp_min_slider,
            self.bsw_temp_max_slider,
            self.bsw_min_jump_slider,
            self.bsw_flash_slider,
            self.bsw_sustain_slider,
            self.bsw_temp_attack_slider,
            self.bsw_bright_attack_slider,
            self.bsw_bright_release_slider,
        ):
            w.valueChanged.connect(self._on_beat_white_changed)
            bsw_layout.addWidget(w)

        bsw_dark_note = QLabel("Dark pulses: same as Beat Sync - a rhythm-synced pause toward black before flashing.")
        bsw_dark_note.setWordWrap(True)
        bsw_layout.addWidget(bsw_dark_note)
        self.bsw_dark_prob_slider = FloatSlider("Dark pulse probability", 0.0, 1.0, bsw.dark_pulse_probability, decimals=2)
        self.bsw_dark_duration_slider = FloatSlider(
            "Dark pulse duration", 10.0, 500.0, bsw.dark_pulse_duration_ms, decimals=0, suffix=" ms"
        )
        self.bsw_dark_depth_slider = FloatSlider("Dark pulse depth", 0.0, 1.0, bsw.dark_pulse_depth, decimals=2)
        for w in (self.bsw_dark_prob_slider, self.bsw_dark_duration_slider, self.bsw_dark_depth_slider):
            w.valueChanged.connect(self._on_beat_white_changed)
            bsw_layout.addWidget(w)

        self.bsw_low_spin.valueChanged.connect(self._on_beat_white_changed)
        self.bsw_high_spin.valueChanged.connect(self._on_beat_white_changed)

        sub_tabs.addTab(bsw_widget, "Beat Sync White")

        # -- Peak Flash mode ------------------------------------------------------------
        peak_widget = QWidget()
        peak_layout = QVBoxLayout(peak_widget)
        pf = cm.peak_flash

        peak_desc_label = QLabel(
            "Reacts to ANY sudden loudness spike (broadband, not just bass), flashes toward "
            "white on strong treble/cymbals, and shows fully-saturated color the rest of the "
            "time. Hue flows continuously and slowly instead of snapping - a smooth 'storytelling' "
            "color arc rather than discrete jumps."
        )
        peak_desc_label.setWordWrap(True)
        peak_layout.addWidget(peak_desc_label)

        peak_detect_row = QHBoxLayout()
        peak_detect_row.addWidget(QLabel("Peak detection band:"))
        self.peak_low_spin = QSpinBox()
        self.peak_low_spin.setRange(20, 20000)
        self.peak_low_spin.setSuffix(" Hz")
        self.peak_low_spin.setValue(int(pf.detect_low_hz))
        peak_detect_row.addWidget(self.peak_low_spin)
        peak_detect_row.addWidget(QLabel("-"))
        self.peak_high_spin = QSpinBox()
        self.peak_high_spin.setRange(20, 20000)
        self.peak_high_spin.setSuffix(" Hz")
        self.peak_high_spin.setValue(int(pf.detect_high_hz))
        peak_detect_row.addWidget(self.peak_high_spin)
        peak_detect_row.addStretch(1)
        peak_layout.addLayout(peak_detect_row)

        self.peak_sensitivity_slider = FloatSlider("Sensitivity", 1.05, 4.0, pf.sensitivity, decimals=2)
        self.peak_min_interval_slider = FloatSlider("Min interval", 20.0, 1000.0, pf.min_interval_ms, decimals=0, suffix=" ms")
        self.peak_min_energy_slider = FloatSlider("Min energy floor", 0.0, 1.0, pf.min_energy)
        for w in (self.peak_sensitivity_slider, self.peak_min_interval_slider, self.peak_min_energy_slider):
            w.valueChanged.connect(self._on_peak_changed)
            peak_layout.addWidget(w)

        treble_row = QHBoxLayout()
        treble_row.addWidget(QLabel("Treble/white band:"))
        self.peak_treble_low_spin = QSpinBox()
        self.peak_treble_low_spin.setRange(20, 20000)
        self.peak_treble_low_spin.setSuffix(" Hz")
        self.peak_treble_low_spin.setValue(int(pf.treble_low_hz))
        treble_row.addWidget(self.peak_treble_low_spin)
        treble_row.addWidget(QLabel("-"))
        self.peak_treble_high_spin = QSpinBox()
        self.peak_treble_high_spin.setRange(20, 20000)
        self.peak_treble_high_spin.setSuffix(" Hz")
        self.peak_treble_high_spin.setValue(int(pf.treble_high_hz))
        treble_row.addWidget(self.peak_treble_high_spin)
        treble_row.addStretch(1)
        peak_layout.addLayout(treble_row)

        self.peak_white_amount_slider = FloatSlider("Whiteness amount", 0.0, 3.0, pf.treble_white_amount)
        self.peak_white_attack_slider = FloatSlider("White attack", 2.0, 300.0, pf.white_attack_ms, decimals=0, suffix=" ms")
        self.peak_white_release_slider = FloatSlider("White release", 20.0, 1500.0, pf.white_release_ms, decimals=0, suffix=" ms")
        for w in (self.peak_white_amount_slider, self.peak_white_attack_slider, self.peak_white_release_slider):
            w.valueChanged.connect(self._on_peak_changed)
            peak_layout.addWidget(w)

        hue_source_row = QHBoxLayout()
        hue_source_row.addWidget(QLabel("Hue source:"))
        self.peak_hue_source_combo = QComboBox()
        self.peak_hue_source_combo.addItems(["drift", "centroid"])
        self.peak_hue_source_combo.setCurrentText(pf.hue_source)
        self.peak_hue_source_combo.currentTextChanged.connect(self._on_peak_changed)
        hue_source_row.addWidget(self.peak_hue_source_combo)
        hue_source_row.addStretch(1)
        peak_layout.addLayout(hue_source_row)

        self.peak_hue_flow_slider = FloatSlider(
            "Color richness (hue flow)", 200.0, 15000.0, pf.hue_flow_ms, decimals=0, suffix=" ms"
        )
        self.peak_drift_speed_slider = FloatSlider("Drift speed", 0.0, 60.0, pf.drift_speed_deg_per_s, decimals=1, suffix=" deg/s")
        self.peak_randomness_slider = FloatSlider("Randomness factor", 0.0, 1.0, pf.randomness, decimals=2)
        self.peak_random_range_slider = FloatSlider(
            "Random jump range", 0.0, 360.0, pf.random_jump_range_deg, decimals=0, suffix=" deg"
        )
        self.peak_saturation_slider = FloatSlider("Saturation", 0.0, 1.0, pf.saturation)
        self.peak_baseline_min_slider = FloatSlider("Baseline brightness min", 0.0, 1.0, pf.baseline_min_brightness)
        self.peak_baseline_max_slider = FloatSlider("Baseline brightness max", 0.0, 1.0, pf.baseline_max_brightness)
        self.peak_flash_brightness_slider = FloatSlider("Flash brightness", 0.0, 1.0, pf.flash_brightness)
        self.peak_flash_attack_slider = FloatSlider("Flash attack", 1.0, 200.0, pf.flash_attack_ms, decimals=0, suffix=" ms")
        self.peak_flash_release_slider = FloatSlider("Flash decay", 30.0, 2000.0, pf.flash_release_ms, decimals=0, suffix=" ms")
        self.peak_loudness_smoothing_slider = FloatSlider(
            "Loudness tracking speed", 20.0, 3000.0, pf.loudness_smoothing_ms, decimals=0, suffix=" ms"
        )
        for w in (
            self.peak_hue_flow_slider,
            self.peak_drift_speed_slider,
            self.peak_randomness_slider,
            self.peak_random_range_slider,
            self.peak_saturation_slider,
            self.peak_baseline_min_slider,
            self.peak_baseline_max_slider,
            self.peak_flash_brightness_slider,
            self.peak_flash_attack_slider,
            self.peak_flash_release_slider,
            self.peak_loudness_smoothing_slider,
        ):
            w.valueChanged.connect(self._on_peak_changed)
            peak_layout.addWidget(w)
            if w is self.peak_random_range_slider:
                peak_randomness_note = QLabel(
                    "Randomness factor: on each detected peak, this is the chance the hue takes a "
                    "random jump (synced to the music) instead of just flowing smoothly - 0 = never "
                    "jumps, 1 = jumps on every peak. The jump still eases in via 'Color richness' above, "
                    "and persists (the story continues from the new hue)."
                )
                peak_randomness_note.setWordWrap(True)
                peak_layout.addWidget(peak_randomness_note)

        for spin in (self.peak_low_spin, self.peak_high_spin, self.peak_treble_low_spin, self.peak_treble_high_spin):
            spin.valueChanged.connect(self._on_peak_changed)

        sub_tabs.addTab(peak_widget, "Peak Flash")

        # -- global ---------------------------------------------------------------------
        global_box = QGroupBox("Global")
        global_layout = QVBoxLayout(global_box)
        curve_row = QHBoxLayout()
        curve_row.addWidget(QLabel("Response curve:"))
        self.curve_combo = QComboBox()
        self.curve_combo.addItems(["linear", "log", "exp2"])
        self.curve_combo.setCurrentText(cm.response_curve)
        self.curve_combo.currentTextChanged.connect(self._on_curve_changed)
        curve_row.addWidget(self.curve_combo)
        curve_row.addStretch(1)
        global_layout.addLayout(curve_row)

        self.threshold_slider = FloatSlider(
            "Min change threshold", 0.0, 0.2, cm.smoothing.min_change_threshold, decimals=3
        )
        self.threshold_slider.valueChanged.connect(self._on_threshold_changed)
        global_layout.addWidget(self.threshold_slider)
        threshold_note = QLabel("Lamp updates smaller than this (0..1 per channel) are skipped to reduce network traffic.")
        threshold_note.setWordWrap(True)
        global_layout.addWidget(threshold_note)

        self.invert_checkbox = QCheckBox("Invert brightness (0 = bright, 1 = black)")
        self.invert_checkbox.setChecked(cm.invert_brightness)
        self.invert_checkbox.toggled.connect(self._on_invert_changed)
        global_layout.addWidget(self.invert_checkbox)
        invert_note = QLabel("Applies to every mode - flips the brightness response so quiet/dark moments light up instead.")
        invert_note.setWordWrap(True)
        global_layout.addWidget(invert_note)

        root.addWidget(global_box)

        # -- presets ------------------------------------------------------------------------
        preset_box = QGroupBox("Presets")
        preset_row = QHBoxLayout(preset_box)
        self.preset_combo = QComboBox()
        self._reload_presets()
        preset_row.addWidget(self.preset_combo, stretch=1)
        load_btn = QPushButton("Load")
        load_btn.clicked.connect(self._load_preset)
        preset_row.addWidget(load_btn)
        save_btn = QPushButton("Save As...")
        save_btn.clicked.connect(self._save_preset)
        preset_row.addWidget(save_btn)
        root.addWidget(preset_box)

        root.addStretch(1)

    # -- handlers -----------------------------------------------------------------------

    def _on_rgb_changed(self, cfg: RGBModeConfig) -> None:
        self.controller.config.color_mapping.rgb = cfg
        self.controller.apply_config_changes()

    def _on_custom_changed(self, cfg: RGBModeConfig) -> None:
        self.controller.config.color_mapping.custom = cfg
        self.controller.apply_config_changes()

    def _on_hsv_changed(self, *_args) -> None:
        hsv = self.controller.config.color_mapping.hsv
        hsv.hue_min_deg = self.hue_min_slider.value()
        hsv.hue_max_deg = self.hue_max_slider.value()
        hsv.brightness_min = self.bright_min_slider.value()
        hsv.brightness_max = self.bright_max_slider.value()
        hsv.saturation_base = self.sat_base_slider.value()
        hsv.saturation_contrast_gain = self.sat_contrast_slider.value()
        hsv.sensitivity = self.hsv_sensitivity_slider.value()
        self.controller.apply_config_changes()

    def _on_beat_changed(self, *_args) -> None:
        bs = self.controller.config.color_mapping.beat_sync
        bs.detect_low_hz = self.beat_low_spin.value()
        bs.detect_high_hz = self.beat_high_spin.value()
        bs.sensitivity = self.beat_sensitivity_slider.value()
        bs.min_interval_ms = self.beat_min_interval_slider.value()
        bs.min_energy = self.beat_min_energy_slider.value()
        bs.hue_mode = self.beat_hue_mode_combo.currentText()
        bs.hue_step_deg = self.beat_hue_step_slider.value()
        bs.min_hue_jump_deg = self.beat_min_jump_slider.value()
        bs.saturation = self.beat_saturation_slider.value()
        bs.flash_brightness = self.beat_flash_slider.value()
        bs.sustain_brightness = self.beat_sustain_slider.value()
        bs.hue_attack_ms = self.beat_hue_attack_slider.value()
        bs.brightness_attack_ms = self.beat_bright_attack_slider.value()
        bs.brightness_release_ms = self.beat_bright_release_slider.value()
        bs.dark_pulse_probability = self.beat_dark_prob_slider.value()
        bs.dark_pulse_duration_ms = self.beat_dark_duration_slider.value()
        bs.dark_pulse_depth = self.beat_dark_depth_slider.value()
        bs.white_pulse_enabled = self.beat_white_pulse_enabled_checkbox.isChecked()
        bs.white_pulse_invert = self.beat_white_pulse_invert_checkbox.isChecked()
        bs.white_pulse_probability = self.beat_white_pulse_prob_slider.value()
        bs.white_pulse_duration_ms = self.beat_white_pulse_duration_slider.value()
        bs.white_pulse_depth = self.beat_white_pulse_depth_slider.value()
        bs.white_pulse_attack_ms = self.beat_white_pulse_attack_slider.value()
        bs.white_pulse_release_ms = self.beat_white_pulse_release_slider.value()
        self.controller.apply_config_changes()

    def _on_beat_white_changed(self, *_args) -> None:
        bsw = self.controller.config.color_mapping.beat_sync_white
        bsw.detect_low_hz = self.bsw_low_spin.value()
        bsw.detect_high_hz = self.bsw_high_spin.value()
        bsw.sensitivity = self.bsw_sensitivity_slider.value()
        bsw.min_interval_ms = self.bsw_min_interval_slider.value()
        bsw.min_energy = self.bsw_min_energy_slider.value()
        bsw.temp_mode = self.bsw_temp_mode_combo.currentText()
        bsw.temp_min = self.bsw_temp_min_slider.value()
        bsw.temp_max = self.bsw_temp_max_slider.value()
        bsw.min_temp_jump = self.bsw_min_jump_slider.value()
        bsw.flash_brightness = self.bsw_flash_slider.value()
        bsw.sustain_brightness = self.bsw_sustain_slider.value()
        bsw.temp_attack_ms = self.bsw_temp_attack_slider.value()
        bsw.brightness_attack_ms = self.bsw_bright_attack_slider.value()
        bsw.brightness_release_ms = self.bsw_bright_release_slider.value()
        bsw.dark_pulse_probability = self.bsw_dark_prob_slider.value()
        bsw.dark_pulse_duration_ms = self.bsw_dark_duration_slider.value()
        bsw.dark_pulse_depth = self.bsw_dark_depth_slider.value()
        self.controller.apply_config_changes()

    def _on_peak_changed(self, *_args) -> None:
        pf = self.controller.config.color_mapping.peak_flash
        pf.detect_low_hz = self.peak_low_spin.value()
        pf.detect_high_hz = self.peak_high_spin.value()
        pf.sensitivity = self.peak_sensitivity_slider.value()
        pf.min_interval_ms = self.peak_min_interval_slider.value()
        pf.min_energy = self.peak_min_energy_slider.value()
        pf.treble_low_hz = self.peak_treble_low_spin.value()
        pf.treble_high_hz = self.peak_treble_high_spin.value()
        pf.treble_white_amount = self.peak_white_amount_slider.value()
        pf.white_attack_ms = self.peak_white_attack_slider.value()
        pf.white_release_ms = self.peak_white_release_slider.value()
        pf.hue_source = self.peak_hue_source_combo.currentText()
        pf.hue_flow_ms = self.peak_hue_flow_slider.value()
        pf.drift_speed_deg_per_s = self.peak_drift_speed_slider.value()
        pf.randomness = self.peak_randomness_slider.value()
        pf.random_jump_range_deg = self.peak_random_range_slider.value()
        pf.saturation = self.peak_saturation_slider.value()
        pf.baseline_min_brightness = self.peak_baseline_min_slider.value()
        pf.baseline_max_brightness = self.peak_baseline_max_slider.value()
        pf.flash_brightness = self.peak_flash_brightness_slider.value()
        pf.flash_attack_ms = self.peak_flash_attack_slider.value()
        pf.flash_release_ms = self.peak_flash_release_slider.value()
        pf.loudness_smoothing_ms = self.peak_loudness_smoothing_slider.value()
        self.controller.apply_config_changes()

    def _on_curve_changed(self, text: str) -> None:
        self.controller.config.color_mapping.response_curve = text
        self.controller.apply_config_changes()

    def _on_invert_changed(self, checked: bool) -> None:
        self.controller.config.color_mapping.invert_brightness = checked
        self.controller.apply_config_changes()

    def _on_threshold_changed(self, value: float) -> None:
        self.controller.config.color_mapping.smoothing.min_change_threshold = value
        self.controller.apply_config_changes()

    # -- presets ---------------------------------------------------------------------------

    def _reload_presets(self) -> None:
        self.preset_combo.clear()
        self.preset_combo.addItems(list(self.controller.config.presets.keys()))

    def _save_preset(self) -> None:
        name, ok = QInputDialog.getText(self, "Save preset", "Preset name:")
        if not ok or not name.strip():
            return
        cfg = self.controller.config
        # Presets capture the full visualization setup: the color mapping
        # mode's own settings, the Chase overlay's global settings, AND which
        # lamps are in the chase (and in what order) - all of it, so loading
        # a preset later fully restores the look, not just the color mode.
        snapshot = {
            "color_mapping": cfg.color_mapping.to_dict(),
            "chase": cfg.chase.to_dict(),
            "per_lamp_chase_orders": {
                device_id: effect.chase_order
                for device_id, effect in cfg.per_lamp_effects.items()
                if effect.chase_order is not None
            },
        }
        cfg.presets[name.strip()] = snapshot
        self._reload_presets()
        self.controller.save_config()

    def _load_preset(self) -> None:
        name = self.preset_combo.currentText()
        if not name:
            return
        data = self.controller.config.presets.get(name)
        if not data:
            QMessageBox.warning(self, "Not found", f"Preset '{name}' not found.")
            return

        if "color_mapping" in data:
            self.controller.config.color_mapping = ColorMappingConfig.from_dict(data["color_mapping"])
            self.controller.config.chase = ChaseEffectConfig.from_dict(data.get("chase", {}))
            for device_id, chase_order in data.get("per_lamp_chase_orders", {}).items():
                self.controller.get_or_create_effect(device_id).chase_order = chase_order
        else:
            # Backward compatibility: presets saved before the Chase overlay
            # existed stored a bare color_mapping dict directly.
            self.controller.config.color_mapping = ColorMappingConfig.from_dict(data)

        self.controller.apply_config_changes()
        QMessageBox.information(
            self, "Preset loaded", f"Loaded preset '{name}'. Reopen the Color Mapping and 8-Band tabs to see updated sliders."
        )
