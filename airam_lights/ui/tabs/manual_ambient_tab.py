"""Ambient Scenes tab for the standalone manual control app: self-looping
animations (color cycle / breathing / color-temperature breathing) driven by
ONE shared PC-side clock, so every selected lamp is synchronized by
construction - no more power-cycling a smart plug and a light switch at the
same moment and hoping the timing lines up.
"""
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
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..manual_controller import ManualController
from ..widgets.hue_slider import HueSlider
from ..widgets.param_slider import FloatSlider

_TABLE_COLUMNS = ["Lamp", "Phase offset (ms)"]


class ManualAmbientTab(QWidget):
    def __init__(self, controller: ManualController, parent=None):
        super().__init__(parent)
        self.controller = controller

        root = QVBoxLayout(self)

        box = QGroupBox("Ambient Scene")
        layout = QVBoxLayout(box)
        layout.addWidget(
            QLabel(
                "A self-looping animation, computed once per tick from one shared clock and sent to "
                "every selected lamp together - always synchronized, no power-cycling needed. This "
                "replaces the bulb's own onboard 'scene' animations (which each run on their own "
                "independent internal clock and can't be synced externally)."
            )
        )
        cfg = controller.config.ambient_scene

        self.enabled_checkbox = QCheckBox("Enabled")
        self.enabled_checkbox.setChecked(cfg.enabled)
        self.enabled_checkbox.toggled.connect(self._on_changed)
        layout.addWidget(self.enabled_checkbox)

        scene_row = QHBoxLayout()
        scene_row.addWidget(QLabel("Scene:"))
        self.scene_combo = QComboBox()
        self.scene_combo.addItems(["color_cycle", "breathing", "temp_breathing"])
        self.scene_combo.setCurrentText(cfg.scene)
        self.scene_combo.currentTextChanged.connect(self._on_changed)
        scene_row.addWidget(self.scene_combo)
        scene_row.addStretch(1)
        layout.addLayout(scene_row)
        layout.addWidget(
            QLabel(
                "color_cycle: all lamps sweep through the full hue wheel together (a synced rainbow). "
                "breathing: brightness pulses smoothly between min and max at a fixed hue (RGB). "
                "temp_breathing: same pulse, but on color temperature (WHITE work_mode, warm<->cool)."
            )
        )

        self.speed_slider = FloatSlider("Speed", 0.01, 2.0, cfg.speed_hz, decimals=3, suffix=" cycles/s")
        layout.addWidget(self.speed_slider)
        layout.addWidget(QLabel("E.g. 0.1 = one full cycle every 10 seconds."))

        self.reverse_checkbox = QCheckBox("Reverse direction")
        self.reverse_checkbox.setChecked(cfg.reverse)
        self.reverse_checkbox.toggled.connect(self._on_changed)
        layout.addWidget(self.reverse_checkbox)
        layout.addWidget(QLabel("Only visibly affects 'color_cycle' (which way it sweeps the hue wheel)."))

        self.hue_slider = HueSlider("Hue (for 'breathing')", cfg.hue)
        self.saturation_slider = FloatSlider("Saturation", 0.0, 1.0, cfg.saturation)
        self.brightness_slider = FloatSlider("Brightness (peak)", 0.0, 1.0, cfg.brightness)
        self.min_brightness_slider = FloatSlider("Min brightness (for 'breathing')", 0.0, 1.0, cfg.min_brightness)
        self.temp_min_slider = FloatSlider("Temp min (for 'temp_breathing')", 0.0, 1.0, cfg.temp_min)
        self.temp_max_slider = FloatSlider("Temp max (for 'temp_breathing')", 0.0, 1.0, cfg.temp_max)
        for w in (
            self.hue_slider,
            self.saturation_slider,
            self.brightness_slider,
            self.min_brightness_slider,
            self.temp_min_slider,
            self.temp_max_slider,
        ):
            w.valueChanged.connect(self._on_changed)
            layout.addWidget(w)

        root.addWidget(box)

        # -- per-lamp phase offset -----------------------------------------------------------
        table_box = QGroupBox("Per-lamp phase offset (optional)")
        table_layout = QVBoxLayout(table_box)
        table_layout.addWidget(
            QLabel(
                "Leave at 0 for every lamp to stay perfectly synchronized (the default, and the whole "
                "point). Give lamps different offsets only if you want a traveling wave look instead."
            )
        )
        self.table = QTableWidget(0, len(_TABLE_COLUMNS))
        self.table.setHorizontalHeaderLabels(_TABLE_COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table_layout.addWidget(self.table)
        root.addWidget(table_box)

        self._populated_lamps = None
        controller.lampsChanged.connect(self._populate_table)
        self._populate_table()

    def _populate_table(self) -> None:
        devices = list(self.controller.lamp_manager.devices.values())
        # lampsChanged also fires every few seconds from the periodic lamp
        # status refresh - rebuilding the cell widgets then would destroy a
        # spinbox mid-edit (focus lost, typed text gone), so only rebuild
        # when the lamp list itself has actually changed.
        lamps = [(dev.config.id, dev.config.name) for dev in devices]
        if lamps == self._populated_lamps:
            return
        self._populated_lamps = lamps
        self.table.setRowCount(len(devices))
        for row, dev in enumerate(devices):
            effect = self.controller.get_or_create_effect(dev.config.id)

            name_item = QTableWidgetItem(dev.config.name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 0, name_item)

            spin = QDoubleSpinBox()
            spin.setRange(-5000.0, 5000.0)
            spin.setDecimals(0)
            spin.setSuffix(" ms")
            spin.setValue(effect.phase_offset_ms)
            spin.valueChanged.connect(lambda v, d=dev.config.id: self._on_offset_changed(d, v))
            self.table.setCellWidget(row, 1, spin)

    def _on_offset_changed(self, device_id: str, value: float) -> None:
        self.controller.get_or_create_effect(device_id).phase_offset_ms = value
        self.controller.apply_config_changes()

    def _on_changed(self, *_args) -> None:
        cfg = self.controller.config.ambient_scene
        cfg.enabled = self.enabled_checkbox.isChecked()
        cfg.scene = self.scene_combo.currentText()
        cfg.speed_hz = self.speed_slider.value()
        cfg.reverse = self.reverse_checkbox.isChecked()
        cfg.hue = self.hue_slider.value()
        cfg.saturation = self.saturation_slider.value()
        cfg.brightness = self.brightness_slider.value()
        cfg.min_brightness = self.min_brightness_slider.value()
        cfg.temp_min = self.temp_min_slider.value()
        cfg.temp_max = self.temp_max_slider.value()
        self.controller.apply_config_changes()
