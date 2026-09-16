"""White Balance tab for the standalone manual control app: set a static
brightness/color-temperature for selected lamps (WHITE work_mode, DPs 22/23
- NOT the RGB colour DP), and optionally run a White Chase effect that
rotates a warm-or-cool region through the lamps instead of an RGB highlight.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..manual_controller import ManualController
from ..widgets.param_slider import FloatSlider


class ManualWhiteTab(QWidget):
    def __init__(self, controller: ManualController, parent=None):
        super().__init__(parent)
        self.controller = controller

        root = QVBoxLayout(self)

        # -- static white balance ------------------------------------------------------
        box = QGroupBox("Set white balance for selected lamps")
        box_layout = QVBoxLayout(box)
        box_layout.addWidget(
            QLabel(
                "Drives the bulb's WHITE work_mode (brightness + color temperature) instead of "
                "RGB color - select lamps in Devices & Setup, then apply here."
            )
        )

        self.temp_slider = FloatSlider("Color temperature", 0.0, 1.0, 0.5, decimals=2)
        box_layout.addWidget(self.temp_slider)
        box_layout.addWidget(QLabel("0.0 = warmest, 1.0 = coolest"))

        self.brightness_slider = FloatSlider("Brightness", 0.0, 1.0, 0.8, decimals=2)
        box_layout.addWidget(self.brightness_slider)

        apply_row = QHBoxLayout()
        apply_btn = QPushButton("Apply to Selected")
        apply_btn.clicked.connect(self._on_apply)
        apply_row.addWidget(apply_btn)
        on_btn = QPushButton("Turn On + Apply")
        on_btn.clicked.connect(self._on_turn_on)
        apply_row.addWidget(on_btn)
        off_btn = QPushButton("Turn Off Selected")
        off_btn.clicked.connect(self._on_turn_off)
        apply_row.addWidget(off_btn)
        apply_row.addStretch(1)
        box_layout.addLayout(apply_row)

        root.addWidget(box)

        # -- white chase ----------------------------------------------------------------
        chase_box = QGroupBox("White Chase (rotating warm/cool region)")
        chase_layout = QVBoxLayout(chase_box)
        chase_layout.addWidget(
            QLabel(
                "Uses the same 'Chase position' numbers set on lamps in the Chase / Rotating Light tab "
                "(lamps sharing a position animate together) - but rotates a color-temperature region "
                "instead of an RGB highlight."
            )
        )
        wc = controller.config.white_chase

        self.enabled_checkbox = QCheckBox("Enabled")
        self.enabled_checkbox.setChecked(wc.enabled)
        self.enabled_checkbox.toggled.connect(self._on_chase_changed)
        chase_layout.addWidget(self.enabled_checkbox)

        rotators_row = QHBoxLayout()
        rotators_row.addWidget(QLabel("Number of rotators:"))
        self.num_rotators_spin = QSpinBox()
        self.num_rotators_spin.setRange(1, 64)  # generous cap, not tied to any specific lamp count
        self.num_rotators_spin.setValue(wc.num_rotators)
        self.num_rotators_spin.valueChanged.connect(self._on_chase_changed)
        rotators_row.addWidget(self.num_rotators_spin)
        rotators_row.addStretch(1)
        chase_layout.addLayout(rotators_row)

        self.speed_slider = FloatSlider(
            "Speed", 0.02, 5.0, wc.speed_rotations_per_s, decimals=3, suffix=" rotations/s"
        )
        self.width_slider = FloatSlider("Highlight width", 0.2, 8.0, wc.width, decimals=2, suffix=" positions")
        self.intensity_slider = FloatSlider("Intensity (brightness boost)", 0.0, 8.0, wc.intensity, decimals=2)
        self.target_temp_slider = FloatSlider("Region (warm..cool)", 0.0, 1.0, wc.target_temp, decimals=2)
        for w in (self.speed_slider, self.width_slider, self.intensity_slider, self.target_temp_slider):
            w.valueChanged.connect(self._on_chase_changed)
            chase_layout.addWidget(w)
        self.reverse_checkbox = QCheckBox("Reverse direction")
        self.reverse_checkbox.setChecked(wc.reverse)
        self.reverse_checkbox.toggled.connect(self._on_chase_changed)
        chase_layout.addWidget(self.reverse_checkbox)
        chase_layout.addWidget(
            QLabel("'Region' picks which color-temperature region sweeps through: 0 = warm, 1 = cool.")
        )

        curve_row = QHBoxLayout()
        curve_row.addWidget(QLabel("Falloff curve:"))
        self.falloff_curve_combo = QComboBox()
        self.falloff_curve_combo.addItems(["linear", "bezier"])
        self.falloff_curve_combo.setCurrentText(wc.falloff_curve)
        self.falloff_curve_combo.currentTextChanged.connect(self._on_chase_changed)
        curve_row.addWidget(self.falloff_curve_combo)
        curve_row.addStretch(1)
        chase_layout.addLayout(curve_row)
        chase_layout.addWidget(
            QLabel("bezier: the highlight dwells near its peak region longer instead of sweeping through at a constant rate.")
        )

        root.addWidget(chase_box)
        root.addStretch(1)

    def _selected_or_warn(self) -> bool:
        if not self.controller.lamp_manager.selected_device_ids():
            QMessageBox.information(self, "No selection", "Select at least one lamp in the Devices & Setup tab first.")
            return False
        return True

    def _on_apply(self) -> None:
        if not self._selected_or_warn():
            return
        self.controller.set_white_for_selected(self.brightness_slider.value(), self.temp_slider.value())

    def _on_turn_on(self) -> None:
        if not self._selected_or_warn():
            return
        import threading

        ids = list(self.controller.lamp_manager.selected_device_ids())

        def _run():
            for device_id in ids:
                dev = self.controller.lamp_manager.devices.get(device_id)
                if dev is None:
                    continue
                try:
                    dev.ensure_white_mode()
                    dev.turn_on(wait_for_ack=False)
                except Exception:
                    pass

        threading.Thread(target=_run, daemon=True).start()
        self.controller.set_white_for_selected(self.brightness_slider.value(), self.temp_slider.value())

    def _on_turn_off(self) -> None:
        if not self._selected_or_warn():
            return
        import threading

        ids = list(self.controller.lamp_manager.selected_device_ids())

        def _run():
            for device_id in ids:
                dev = self.controller.lamp_manager.devices.get(device_id)
                if dev is None:
                    continue
                try:
                    dev.turn_off(wait_for_ack=False)
                except Exception:
                    pass

        threading.Thread(target=_run, daemon=True).start()

    def _on_chase_changed(self, *_args) -> None:
        wc = self.controller.config.white_chase
        wc.enabled = self.enabled_checkbox.isChecked()
        wc.num_rotators = self.num_rotators_spin.value()
        wc.speed_rotations_per_s = self.speed_slider.value()
        wc.width = self.width_slider.value()
        wc.intensity = self.intensity_slider.value()
        wc.target_temp = self.target_temp_slider.value()
        wc.reverse = self.reverse_checkbox.isChecked()
        wc.falloff_curve = self.falloff_curve_combo.currentText()
        self.controller.apply_config_changes()
        if wc.enabled:
            self.controller.manual.mode = "white"
