"""A labeled float slider (QSlider + QDoubleSpinBox kept in sync).

Used everywhere in the color-mapping / smoothing / per-lamp UI so those tabs
don't have to hand-roll slider<->spinbox syncing repeatedly.
"""
from __future__ import annotations

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QDoubleSpinBox, QHBoxLayout, QLabel, QSlider, QWidget

_STEPS = 1000


class FloatSlider(QWidget):
    valueChanged = Signal(float)

    def __init__(
        self,
        label: str,
        minimum: float,
        maximum: float,
        value: float = 0.0,
        decimals: int = 2,
        suffix: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self._min = minimum
        self._max = maximum
        self._updating = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._label = QLabel(label)
        self._label.setMinimumWidth(120)
        layout.addWidget(self._label)

        self._slider = QSlider(Qt.Horizontal)
        self._slider.setRange(0, _STEPS)
        layout.addWidget(self._slider, stretch=1)

        self._spin = QDoubleSpinBox()
        self._spin.setRange(minimum, maximum)
        self._spin.setDecimals(decimals)
        self._spin.setSuffix(suffix)
        self._spin.setFixedWidth(90)
        layout.addWidget(self._spin)

        self._slider.valueChanged.connect(self._on_slider)
        self._spin.valueChanged.connect(self._on_spin)
        self.set_value(value)

    def _on_slider(self, step: int) -> None:
        if self._updating:
            return
        value = self._min + (self._max - self._min) * (step / _STEPS)
        self._updating = True
        self._spin.setValue(value)
        self._updating = False
        self.valueChanged.emit(value)

    def _on_spin(self, value: float) -> None:
        if self._updating:
            return
        step = int(round((value - self._min) / (self._max - self._min) * _STEPS)) if self._max > self._min else 0
        self._updating = True
        self._slider.setValue(step)
        self._updating = False
        self.valueChanged.emit(value)

    def value(self) -> float:
        return self._spin.value()

    def set_value(self, value: float) -> None:
        self._updating = True
        value = max(self._min, min(self._max, value))
        self._spin.setValue(value)
        step = int(round((value - self._min) / (self._max - self._min) * _STEPS)) if self._max > self._min else 0
        self._slider.setValue(step)
        self._updating = False
