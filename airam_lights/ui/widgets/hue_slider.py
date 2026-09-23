"""A hue picker: the same slider+spinbox as FloatSlider, plus a clickable
color swatch that opens a proper color dialog for visually picking a hue
(0..360 degrees) instead of typing a number. Drop-in replacement for
FloatSlider wherever a control represents an actual hue value (not a hue
*step*/delta, which a color swatch can't meaningfully represent) - same
`.value()` / `.set_value()` / `.valueChanged` API.

Only the hue is taken from the picked color - saturation/brightness are
deliberately ignored, since those are always controlled by their own
separate sliders elsewhere in this app.
"""
from __future__ import annotations

from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QColorDialog, QDoubleSpinBox, QHBoxLayout, QLabel, QPushButton, QSlider, QWidget

_STEPS = 360


class HueSlider(QWidget):
    valueChanged = Signal(float)

    def __init__(self, label: str, value: float = 0.0, tooltip: str = "", parent=None):
        super().__init__(parent)
        self._updating = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        if tooltip:
            self.setToolTip(tooltip)

        self._label = QLabel(label)
        self._label.setMinimumWidth(120)
        layout.addWidget(self._label)

        self._slider = QSlider(Qt.Horizontal)
        self._slider.setRange(0, _STEPS)
        layout.addWidget(self._slider, stretch=1)

        self._spin = QDoubleSpinBox()
        self._spin.setRange(0.0, 360.0)
        self._spin.setDecimals(0)
        self._spin.setSuffix(" deg")
        self._spin.setFixedWidth(80)
        layout.addWidget(self._spin)

        self._swatch = QPushButton()
        self._swatch.setFixedSize(30, 22)
        self._swatch.setToolTip("Pick a hue visually")
        self._swatch.clicked.connect(self._on_pick_color)
        layout.addWidget(self._swatch)

        self._slider.valueChanged.connect(self._on_slider)
        self._spin.valueChanged.connect(self._on_spin)
        self.set_value(value)

    def _swatch_color(self) -> QColor:
        return QColor.fromHsv(int(round(self.value())) % 360, 255, 255)

    def _update_swatch(self) -> None:
        c = self._swatch_color()
        self._swatch.setStyleSheet(f"background-color: {c.name()}; border: 1px solid #555;")

    def _on_slider(self, step: int) -> None:
        if self._updating:
            return
        self._updating = True
        self._spin.setValue(float(step))
        self._updating = False
        self._update_swatch()
        self.valueChanged.emit(float(step))

    def _on_spin(self, value: float) -> None:
        if self._updating:
            return
        self._updating = True
        self._slider.setValue(int(round(value)))
        self._updating = False
        self._update_swatch()
        self.valueChanged.emit(value)

    def _on_pick_color(self) -> None:
        picked = QColorDialog.getColor(self._swatch_color(), self, "Pick a hue")
        if not picked.isValid():
            return
        hue = picked.hue()  # 0..359, or -1 for an achromatic (gray/white/black) pick
        self.set_value(float(hue) if hue >= 0 else 0.0)

    def value(self) -> float:
        return self._spin.value()

    def set_value(self, value: float) -> None:
        """Programmatically set the value WITHOUT emitting valueChanged -
        matches FloatSlider's contract, so loading a preset/config into the
        UI never immediately writes the same value straight back out."""
        self._updating = True
        value = max(0.0, min(360.0, value))
        self._spin.setValue(value)
        self._slider.setValue(int(round(value)))
        self._updating = False
        self._update_swatch()
