"""Editor for one ChannelMap (frequency range -> gain/min/max/gamma for one
output channel). Used three times for RGB mode and three times for Custom
mode - the two modes share this exact mechanism (see color/mapping.py)."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFormLayout, QGroupBox, QSpinBox

from ...config.schema import ChannelMap
from .param_slider import FloatSlider


class ChannelMapEditor(QGroupBox):
    changed = Signal()

    def __init__(self, title: str, channel_map: ChannelMap, parent=None):
        super().__init__(title, parent)
        self._updating = False

        form = QFormLayout(self)

        self.low_spin = QSpinBox()
        self.low_spin.setRange(20, 20000)
        self.low_spin.setSuffix(" Hz")
        self.low_spin.setValue(int(channel_map.low_hz))
        self.low_spin.valueChanged.connect(self._emit)
        form.addRow("Low:", self.low_spin)

        self.high_spin = QSpinBox()
        self.high_spin.setRange(20, 20000)
        self.high_spin.setSuffix(" Hz")
        self.high_spin.setValue(int(channel_map.high_hz))
        self.high_spin.valueChanged.connect(self._emit)
        form.addRow("High:", self.high_spin)

        self.gain_slider = FloatSlider("Gain", 0.0, 4.0, channel_map.gain)
        self.gain_slider.valueChanged.connect(self._emit)
        form.addRow(self.gain_slider)

        self.min_slider = FloatSlider("Min level", 0.0, 1.0, channel_map.min_level)
        self.min_slider.valueChanged.connect(self._emit)
        form.addRow(self.min_slider)

        self.max_slider = FloatSlider("Max level", 0.0, 1.0, channel_map.max_level)
        self.max_slider.valueChanged.connect(self._emit)
        form.addRow(self.max_slider)

        self.gamma_slider = FloatSlider("Gamma", 0.2, 4.0, channel_map.gamma)
        self.gamma_slider.valueChanged.connect(self._emit)
        form.addRow(self.gamma_slider)

    def _emit(self, *_args) -> None:
        if not self._updating:
            self.changed.emit()

    def to_channel_map(self) -> ChannelMap:
        return ChannelMap(
            low_hz=float(self.low_spin.value()),
            high_hz=float(self.high_spin.value()),
            gain=self.gain_slider.value(),
            min_level=self.min_slider.value(),
            max_level=self.max_slider.value(),
            gamma=self.gamma_slider.value(),
        )

    def set_channel_map(self, channel_map: ChannelMap) -> None:
        self._updating = True
        self.low_spin.setValue(int(channel_map.low_hz))
        self.high_spin.setValue(int(channel_map.high_hz))
        self.gain_slider.set_value(channel_map.gain)
        self.min_slider.set_value(channel_map.min_level)
        self.max_slider.set_value(channel_map.max_level)
        self.gamma_slider.set_value(channel_map.gamma)
        self._updating = False
