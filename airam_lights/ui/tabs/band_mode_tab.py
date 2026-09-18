"""8-Band Spectrum mode tab: per-band frequency ranges (one band per lamp by
default), spectrum-mode color parameters, and the per-lamp effects table
(band assignment, phase offset, brightness/saturation/hue/sensitivity
multipliers) that turns a set of identical bulbs into a coordinated
installation instead of identical copies of the same signal.

Split into inner sub-tabs (Bands & Spectrum / Per-Lamp Effects / Chase
Overlay) rather than one long scrolling page - the Chase overlay alone has
~20 controls, which used to force a single giant column everything else sat
below, and the per-lamp table was squeezed down to a sizeHint of just a row
or two (its own inner scrollbar buried inside the page's outer one). Giving
each concern its own page keeps any one page's scroll distance short, and
lets the per-lamp table claim real vertical space the same way the Devices
& Setup tab's lamp list does."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ...config.schema import BandDefinition, PerLampEffect
from ..controller import AppController
from ..widgets.hue_slider import HueSlider
from ..widgets.param_slider import FloatSlider

_BAND_COLUMNS = ["Name", "Low (Hz)", "High (Hz)"]
_EFFECT_COLUMNS = [
    "Lamp",
    "Band",
    "Phase offset (ms)",
    "Brightness x",
    "Saturation x",
    "Hue offset (deg)",
    "Sensitivity x",
    "Chase order",
    "Chase dwell x",
]


def _scroll_page() -> "tuple[QWidget, QVBoxLayout]":
    """A tab page that's just a QScrollArea wrapping a QVBoxLayout - the
    common shell for pages whose content can outgrow the window height.
    Returns (page_widget_to_add_to_the_tab, layout_to_fill_with_content)."""
    page = QWidget()
    page_layout = QVBoxLayout(page)
    page_layout.setContentsMargins(0, 0, 0, 0)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    page_layout.addWidget(scroll)
    inner = QWidget()
    scroll.setWidget(inner)
    return page, QVBoxLayout(inner)


class BandModeTab(QWidget):
    def __init__(self, controller: AppController, parent=None):
        super().__init__(parent)
        self.controller = controller

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        sub_tabs = QTabWidget()
        outer.addWidget(sub_tabs)

        bands_page, bands_root = _scroll_page()
        sub_tabs.addTab(bands_page, "Bands && Spectrum")

        effects_page = QWidget()
        effects_root = QVBoxLayout(effects_page)
        sub_tabs.addTab(effects_page, "Per-Lamp Effects")

        chase_page, chase_root = _scroll_page()
        sub_tabs.addTab(chase_page, "Chase Overlay")

        # -- band definitions -------------------------------------------------------
        band_box = QGroupBox("8-Band definitions (default: one band per lamp)")
        band_layout = QVBoxLayout(band_box)
        self.band_table = QTableWidget(len(controller.config.bands_8), len(_BAND_COLUMNS))
        self.band_table.setHorizontalHeaderLabels(_BAND_COLUMNS)
        self.band_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        # A QTableWidget's sizeHint doesn't grow with its row count, so
        # without this it defaults to showing only ~5 of the 8 bands behind
        # its own inner scrollbar - Expanding + a layout stretch factor
        # below lets it actually claim the page's spare vertical space.
        self.band_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._populate_band_table()
        band_layout.addWidget(self.band_table)
        bands_root.addWidget(band_box, stretch=1)

        # -- spectrum mode color params -----------------------------------------------
        color_box = QGroupBox("Spectrum mode appearance")
        color_layout = QVBoxLayout(color_box)
        spec = controller.config.color_mapping.spectrum
        self.base_hue_slider = HueSlider("Base hue", spec.base_hue_deg)
        self.hue_step_slider = FloatSlider("Hue step across bands", -60.0, 60.0, spec.hue_step_deg, decimals=0, suffix=" deg")
        self.saturation_slider = FloatSlider("Saturation", 0.0, 1.0, spec.saturation)
        self.min_bright_slider = FloatSlider("Min brightness", 0.0, 1.0, spec.min_brightness)
        self.max_bright_slider = FloatSlider("Max brightness", 0.0, 1.0, spec.max_brightness)
        self.spec_sensitivity_slider = FloatSlider("Sensitivity", 0.1, 4.0, spec.sensitivity)
        for w in (
            self.base_hue_slider,
            self.hue_step_slider,
            self.saturation_slider,
            self.min_bright_slider,
            self.max_bright_slider,
            self.spec_sensitivity_slider,
        ):
            w.valueChanged.connect(self._on_spectrum_changed)
            color_layout.addWidget(w)
        self.drive_sat_checkbox = QCheckBox("Band level also modulates saturation")
        self.drive_sat_checkbox.setChecked(spec.drive_saturation_too)
        self.drive_sat_checkbox.toggled.connect(self._on_spectrum_changed)
        color_layout.addWidget(self.drive_sat_checkbox)
        bands_root.addWidget(color_box)

        # -- per-lamp effects -----------------------------------------------------------
        # Own page, given stretch=1 below (not squeezed inside a scroll area
        # alongside everything else) so it actually claims the page's full
        # height, the same way the Devices & Setup tab's lamp list does -
        # showing every lamp at once instead of one row behind an inner
        # scrollbar.
        effects_box = QGroupBox("Per-lamp effects (applies in every mode)")
        effects_layout = QVBoxLayout(effects_box)
        effects_label = QLabel(
            "Set band assignment (8-Band mode), a small delay for wave/chase effects, "
            "per-lamp brightness/saturation/hue/sensitivity multipliers, and 'Chase dwell x' "
            "- how long the Chase overlay's highlight lingers at this lamp's chase position "
            "relative to others (1.0 = default; lower it for a position with several lamps "
            "at once, e.g. a multi-spot ceiling fixture, if the highlight feels like it's "
            "dwelling there too long)."
        )
        effects_label.setWordWrap(True)
        effects_layout.addWidget(effects_label)
        self.effects_table = QTableWidget(0, len(_EFFECT_COLUMNS))
        self.effects_table.setHorizontalHeaderLabels(_EFFECT_COLUMNS)
        self.effects_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        # With this many columns, equal-share Stretch can squeeze a numeric
        # column below the width a spinbox needs to show its up/down
        # buttons - they'd still work via scroll wheel or typing, but be
        # invisible/undiscoverable. Floor every column's width so the
        # buttons always have room; the table scrolls horizontally instead
        # of ever going narrower than that.
        self.effects_table.horizontalHeader().setMinimumSectionSize(70)
        self.effects_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        effects_layout.addWidget(self.effects_table)
        effects_root.addWidget(effects_box, stretch=1)

        # -- chase / rotating light overlay ----------------------------------------------
        chase_box = QGroupBox("Chase / Rotating Light overlay (works on top of ANY mode above)")
        chase_outer_layout = QVBoxLayout(chase_box)
        chase_intro_label = QLabel(
            "Set 'Chase order' (0, 1, 2, ...) on the lamps in the Per-Lamp Effects tab to include "
            "them in the rotation, in that order - a moving highlight travels through them, "
            "overlaid on whatever the active mode is already showing."
        )
        chase_intro_label.setWordWrap(True)
        chase_outer_layout.addWidget(chase_intro_label)
        # Two side-by-side columns instead of one long one - roughly halves
        # how far you need to scroll to reach any given control here. Each
        # column is a real QWidget (not a bare layout handed to addLayout())
        # - word-wrapped QLabels below need their own widget's resize events
        # to recompute wrapped height correctly at the column's actual
        # width; nested directly as bare layouts, they can mis-measure and
        # clip their last line instead of wrapping to it.
        columns_row = QHBoxLayout()
        chase_outer_layout.addLayout(columns_row)
        speed_widget = QWidget()
        appearance_widget = QWidget()
        speed_col = QVBoxLayout(speed_widget)
        appearance_col = QVBoxLayout(appearance_widget)
        speed_col.setContentsMargins(0, 0, 0, 0)
        appearance_col.setContentsMargins(0, 0, 0, 0)
        columns_row.addWidget(speed_widget, 1)
        columns_row.addWidget(appearance_widget, 1)
        ch = controller.config.chase

        # -- left column: enable/speed/sync -----------------------------------------
        self.chase_enabled_checkbox = QCheckBox("Enabled")
        self.chase_enabled_checkbox.setChecked(ch.enabled)
        self.chase_enabled_checkbox.toggled.connect(self._on_chase_changed)
        speed_col.addWidget(self.chase_enabled_checkbox)

        rotators_row = QHBoxLayout()
        rotators_row.addWidget(QLabel("Number of rotators:"))
        self.chase_num_rotators_spin = QSpinBox()
        self.chase_num_rotators_spin.setRange(1, 64)  # generous cap, not tied to any specific lamp count
        self.chase_num_rotators_spin.setValue(ch.num_rotators)
        self.chase_num_rotators_spin.valueChanged.connect(self._on_chase_changed)
        rotators_row.addWidget(self.chase_num_rotators_spin)
        rotators_row.addStretch(1)
        speed_col.addLayout(rotators_row)
        rotators_label = QLabel(
            "How many highlights travel the loop at once, evenly spaced and moving together - "
            "2 puts them on opposite sides of the loop, 3 spaces them a third of the way apart, etc."
        )
        rotators_label.setWordWrap(True)
        speed_col.addWidget(rotators_label)

        self.chase_speed_slider = FloatSlider(
            "Speed (constant)", 0.02, 5.0, ch.speed_rotations_per_s, decimals=3, suffix=" rotations/s"
        )
        self.chase_speed_slider.valueChanged.connect(self._on_chase_changed)
        speed_col.addWidget(self.chase_speed_slider)
        speed_label = QLabel(
            "This is full laps around all the chase-ordered lamps per second - e.g. 0.5 = one full "
            "loop every 2 seconds, regardless of how many lamps are in the chase."
        )
        speed_label.setWordWrap(True)
        speed_col.addWidget(speed_label)

        self.chase_reverse_checkbox = QCheckBox("Reverse direction")
        self.chase_reverse_checkbox.setChecked(ch.reverse)
        self.chase_reverse_checkbox.toggled.connect(self._on_chase_changed)
        speed_col.addWidget(self.chase_reverse_checkbox)

        sync_mode_row = QHBoxLayout()
        sync_mode_row.addWidget(QLabel("Speed source:"))
        self.chase_sync_mode_combo = QComboBox()
        self.chase_sync_mode_combo.addItems(["off", "beat", "intensity_peak"])
        self.chase_sync_mode_combo.setCurrentText(ch.sync_mode)
        self.chase_sync_mode_combo.currentTextChanged.connect(self._on_chase_changed)
        sync_mode_row.addWidget(self.chase_sync_mode_combo)
        sync_mode_row.addStretch(1)
        speed_col.addLayout(sync_mode_row)
        sync_mode_label = QLabel(
            "off: constant speed above, ignoring audio. beat: sits still and only advances on a "
            "detected bass-drum-style hit. intensity_peak: sits still and only advances on ANY sudden "
            "loudness spike (better for tracks without a strong, steady beat). Both hit-based modes "
            "never drift on their own between hits - they move only with the actual rhythm."
        )
        sync_mode_label.setWordWrap(True)
        speed_col.addWidget(sync_mode_label)

        self.chase_multiplier_slider = FloatSlider(
            "Steps per hit", 0.125, 8.0, ch.beat_multiplier, decimals=3, suffix="x"
        )
        self.chase_multiplier_slider.valueChanged.connect(self._on_chase_changed)
        speed_col.addWidget(self.chase_multiplier_slider)
        multiplier_label = QLabel(
            "1 = one lamp-step per hit, 2 = twice as fast (two steps per hit), 0.5 = half as fast "
            "(one step every two hits). Applies to both beat and intensity_peak modes."
        )
        multiplier_label.setWordWrap(True)
        speed_col.addWidget(multiplier_label)

        beat_detect_row = QHBoxLayout()
        beat_detect_row.addWidget(QLabel("Beat detection band:"))
        self.chase_beat_low_spin = QSpinBox()
        self.chase_beat_low_spin.setRange(20, 20000)
        self.chase_beat_low_spin.setSuffix(" Hz")
        self.chase_beat_low_spin.setValue(int(ch.beat_detect_low_hz))
        beat_detect_row.addWidget(self.chase_beat_low_spin)
        beat_detect_row.addWidget(QLabel("-"))
        self.chase_beat_high_spin = QSpinBox()
        self.chase_beat_high_spin.setRange(20, 20000)
        self.chase_beat_high_spin.setSuffix(" Hz")
        self.chase_beat_high_spin.setValue(int(ch.beat_detect_high_hz))
        beat_detect_row.addWidget(self.chase_beat_high_spin)
        beat_detect_row.addStretch(1)
        speed_col.addLayout(beat_detect_row)

        self.chase_beat_sensitivity_slider = FloatSlider("Beat sensitivity", 1.05, 4.0, ch.beat_sensitivity, decimals=2)
        self.chase_beat_min_interval_slider = FloatSlider(
            "Beat min interval", 30.0, 1000.0, ch.beat_min_interval_ms, decimals=0, suffix=" ms"
        )

        peak_detect_row = QHBoxLayout()
        peak_detect_row.addWidget(QLabel("Intensity-peak detection band:"))
        self.chase_peak_low_spin = QSpinBox()
        self.chase_peak_low_spin.setRange(20, 20000)
        self.chase_peak_low_spin.setSuffix(" Hz")
        self.chase_peak_low_spin.setValue(int(ch.peak_detect_low_hz))
        peak_detect_row.addWidget(self.chase_peak_low_spin)
        peak_detect_row.addWidget(QLabel("-"))
        self.chase_peak_high_spin = QSpinBox()
        self.chase_peak_high_spin.setRange(20, 20000)
        self.chase_peak_high_spin.setSuffix(" Hz")
        self.chase_peak_high_spin.setValue(int(ch.peak_detect_high_hz))
        peak_detect_row.addWidget(self.chase_peak_high_spin)
        peak_detect_row.addStretch(1)
        speed_col.addLayout(peak_detect_row)

        self.chase_peak_sensitivity_slider = FloatSlider("Peak sensitivity", 1.05, 4.0, ch.peak_sensitivity, decimals=2)
        self.chase_peak_min_interval_slider = FloatSlider(
            "Peak min interval", 30.0, 1000.0, ch.peak_min_interval_ms, decimals=0, suffix=" ms"
        )
        for w in (
            self.chase_beat_sensitivity_slider,
            self.chase_beat_min_interval_slider,
            self.chase_peak_sensitivity_slider,
            self.chase_peak_min_interval_slider,
        ):
            w.valueChanged.connect(self._on_chase_changed)
            speed_col.addWidget(w)
        speed_col.addStretch(1)

        # -- right column: width/intensity/falloff/color appearance -----------------
        self.chase_width_slider = FloatSlider("Highlight width", 0.2, 8.0, ch.width, decimals=2, suffix=" lamps")
        self.chase_intensity_slider = FloatSlider("Intensity (brightness boost)", 0.0, 8.0, ch.intensity, decimals=2)
        for w in (self.chase_width_slider, self.chase_intensity_slider):
            w.valueChanged.connect(self._on_chase_changed)
            appearance_col.addWidget(w)
        width_intensity_label = QLabel(
            "Lower width = a crisper, single-lamp-like highlight (easier to see as 'one dot moving'). "
            "Intensity multiplies the lamp's own current brightness at the highlight's peak (never adds "
            "light where the active mode says black - e.g. a Beat Sync dark pulse stays dark)."
        )
        width_intensity_label.setWordWrap(True)
        appearance_col.addWidget(width_intensity_label)

        chase_curve_row = QHBoxLayout()
        chase_curve_row.addWidget(QLabel("Falloff curve:"))
        self.chase_falloff_curve_combo = QComboBox()
        self.chase_falloff_curve_combo.addItems(["linear", "bezier"])
        self.chase_falloff_curve_combo.setCurrentText(ch.falloff_curve)
        self.chase_falloff_curve_combo.currentTextChanged.connect(self._on_chase_changed)
        chase_curve_row.addWidget(self.chase_falloff_curve_combo)
        chase_curve_row.addStretch(1)
        appearance_col.addLayout(chase_curve_row)
        curve_label = QLabel(
            "linear: constant-rate falloff - the peak color is a single fleeting instant. bezier: an "
            "eased S-curve that dwells near the peak (and near the background) longer - try this if "
            "the highlight feels like it flies by too quickly."
        )
        curve_label.setWordWrap(True)
        appearance_col.addWidget(curve_label)

        color_mode_row = QHBoxLayout()
        color_mode_row.addWidget(QLabel("Chase color:"))
        self.chase_color_mode_combo = QComboBox()
        self.chase_color_mode_combo.addItems(["custom", "complementary", "hue_shift"])
        self.chase_color_mode_combo.setCurrentText(ch.color_mode)
        self.chase_color_mode_combo.currentTextChanged.connect(self._on_chase_changed)
        color_mode_row.addWidget(self.chase_color_mode_combo)
        color_mode_row.addStretch(1)
        appearance_col.addLayout(color_mode_row)
        color_mode_label = QLabel(
            "custom: a fixed color you set below. complementary: the opposite hue of each lamp's own "
            "color. hue_shift: each chase position shows a different hue (a rainbow trail) starting "
            "from the custom hue below, stepped by 'Hue shift step' per position."
        )
        color_mode_label.setWordWrap(True)
        appearance_col.addWidget(color_mode_label)

        self.chase_hue_slider = HueSlider("Custom hue", ch.custom_hue_deg)
        self.chase_sat_slider = FloatSlider("Custom saturation", 0.0, 1.0, ch.custom_saturation)
        self.chase_hue_shift_slider = FloatSlider(
            "Hue shift step (for 'hue_shift')", 1.0, 180.0, ch.hue_shift_step_deg, decimals=1, suffix=" deg"
        )
        for w in (self.chase_hue_slider, self.chase_sat_slider, self.chase_hue_shift_slider):
            w.valueChanged.connect(self._on_chase_changed)
            appearance_col.addWidget(w)
        appearance_col.addStretch(1)

        self.chase_beat_low_spin.valueChanged.connect(self._on_chase_changed)
        self.chase_beat_high_spin.valueChanged.connect(self._on_chase_changed)
        self.chase_peak_low_spin.valueChanged.connect(self._on_chase_changed)
        self.chase_peak_high_spin.valueChanged.connect(self._on_chase_changed)

        chase_root.addWidget(chase_box)

        controller.lampsChanged.connect(self._populate_effects_table)
        self._populate_effects_table()

    # -- band definitions --------------------------------------------------------------

    def _populate_band_table(self) -> None:
        self.band_table.blockSignals(True)
        for row, band in enumerate(self.controller.config.bands_8):
            name_item = QTableWidgetItem(band.name)
            self.band_table.setItem(row, 0, name_item)

            low_spin = QSpinBox()
            low_spin.setRange(1, 20000)
            low_spin.setValue(int(band.low_hz))
            low_spin.valueChanged.connect(self._on_band_table_changed)
            self.band_table.setCellWidget(row, 1, low_spin)

            high_spin = QSpinBox()
            high_spin.setRange(1, 20000)
            high_spin.setValue(int(band.high_hz))
            high_spin.valueChanged.connect(self._on_band_table_changed)
            self.band_table.setCellWidget(row, 2, high_spin)
        self.band_table.blockSignals(False)
        self.band_table.itemChanged.connect(self._on_band_table_changed)

    def _on_band_table_changed(self, *_args) -> None:
        bands = []
        for row in range(self.band_table.rowCount()):
            name_item = self.band_table.item(row, 0)
            low_widget = self.band_table.cellWidget(row, 1)
            high_widget = self.band_table.cellWidget(row, 2)
            if name_item is None or low_widget is None or high_widget is None:
                continue
            bands.append(BandDefinition(name=name_item.text() or f"Band {row+1}", low_hz=low_widget.value(), high_hz=high_widget.value()))
        if bands:
            self.controller.config.bands_8 = bands
            self.controller.apply_config_changes()

    # -- spectrum params ------------------------------------------------------------------

    def _on_spectrum_changed(self, *_args) -> None:
        spec = self.controller.config.color_mapping.spectrum
        spec.base_hue_deg = self.base_hue_slider.value()
        spec.hue_step_deg = self.hue_step_slider.value()
        spec.saturation = self.saturation_slider.value()
        spec.min_brightness = self.min_bright_slider.value()
        spec.max_brightness = self.max_bright_slider.value()
        spec.sensitivity = self.spec_sensitivity_slider.value()
        spec.drive_saturation_too = self.drive_sat_checkbox.isChecked()
        self.controller.apply_config_changes()

    # -- per-lamp effects table -------------------------------------------------------------

    def _populate_effects_table(self) -> None:
        devices = list(self.controller.lamp_manager.devices.values())
        self.effects_table.setRowCount(len(devices))
        num_bands = len(self.controller.config.bands_8)

        for row, dev in enumerate(devices):
            effect = self.controller.get_or_create_effect(dev.config.id)

            name_item = QTableWidgetItem(dev.config.name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            self.effects_table.setItem(row, 0, name_item)

            band_combo = QComboBox()
            band_combo.addItem("Auto", None)
            for i in range(num_bands):
                band_combo.addItem(f"Band {i+1}", i)
            if effect.band_index is not None:
                idx = band_combo.findData(effect.band_index)
                if idx >= 0:
                    band_combo.setCurrentIndex(idx)
            band_combo.currentIndexChanged.connect(lambda _i, d=dev.config.id, c=band_combo: self._on_effect_changed(d, "band_index", c.currentData()))
            self.effects_table.setCellWidget(row, 1, band_combo)

            self._add_spin(row, 2, dev.config.id, "phase_offset_ms", -500.0, 500.0, effect.phase_offset_ms)
            self._add_spin(row, 3, dev.config.id, "brightness_mult", 0.0, 2.0, effect.brightness_mult)
            self._add_spin(row, 4, dev.config.id, "saturation_mult", 0.0, 2.0, effect.saturation_mult)
            self._add_spin(row, 5, dev.config.id, "hue_offset_deg", -180.0, 180.0, effect.hue_offset_deg)
            self._add_spin(row, 6, dev.config.id, "sensitivity_mult", 0.0, 2.0, effect.sensitivity_mult)

            chase_spin = QSpinBox()
            chase_spin.setRange(-1, max(7, len(devices) - 1))
            chase_spin.setSpecialValueText("Off")
            chase_spin.setValue(effect.chase_order if effect.chase_order is not None else -1)
            chase_spin.valueChanged.connect(
                lambda v, d=dev.config.id: self._on_effect_changed(d, "chase_order", (v if v >= 0 else None))
            )
            self.effects_table.setCellWidget(row, 7, chase_spin)

            self._add_spin(row, 8, dev.config.id, "chase_dwell_mult", 0.1, 10.0, effect.chase_dwell_mult)

    def _add_spin(self, row: int, col: int, device_id: str, attr: str, lo: float, hi: float, value: float) -> None:
        spin = QDoubleSpinBox()
        spin.setRange(lo, hi)
        spin.setDecimals(2)
        spin.setValue(value)
        # Explicit (Qt's default already, but stated here so it's obvious and
        # never silently lost) - these are always visibly clickable, not just
        # scroll-wheel/type-only.
        spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.UpDownArrows)
        spin.valueChanged.connect(lambda v, d=device_id, a=attr: self._on_effect_changed(d, a, v))
        self.effects_table.setCellWidget(row, col, spin)

    def _on_effect_changed(self, device_id: str, attr: str, value) -> None:
        effect = self.controller.get_or_create_effect(device_id)
        setattr(effect, attr, value)
        self.controller.apply_config_changes()

    # -- chase overlay --------------------------------------------------------------------

    def _on_chase_changed(self, *_args) -> None:
        ch = self.controller.config.chase
        ch.enabled = self.chase_enabled_checkbox.isChecked()
        ch.num_rotators = self.chase_num_rotators_spin.value()
        ch.speed_rotations_per_s = self.chase_speed_slider.value()
        ch.reverse = self.chase_reverse_checkbox.isChecked()
        ch.sync_mode = self.chase_sync_mode_combo.currentText()
        ch.beat_multiplier = self.chase_multiplier_slider.value()
        ch.beat_detect_low_hz = self.chase_beat_low_spin.value()
        ch.beat_detect_high_hz = self.chase_beat_high_spin.value()
        ch.beat_sensitivity = self.chase_beat_sensitivity_slider.value()
        ch.beat_min_interval_ms = self.chase_beat_min_interval_slider.value()
        ch.peak_detect_low_hz = self.chase_peak_low_spin.value()
        ch.peak_detect_high_hz = self.chase_peak_high_spin.value()
        ch.peak_sensitivity = self.chase_peak_sensitivity_slider.value()
        ch.peak_min_interval_ms = self.chase_peak_min_interval_slider.value()
        ch.width = self.chase_width_slider.value()
        ch.intensity = self.chase_intensity_slider.value()
        ch.falloff_curve = self.chase_falloff_curve_combo.currentText()
        ch.color_mode = self.chase_color_mode_combo.currentText()
        ch.custom_hue_deg = self.chase_hue_slider.value()
        ch.custom_saturation = self.chase_sat_slider.value()
        ch.hue_shift_step_deg = self.chase_hue_shift_slider.value()
        self.controller.apply_config_changes()
