"""One row representing a single lamp: selection checkbox, online dot, name,
live color swatch, and latency readout."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QFrame, QHBoxLayout, QLabel, QSizePolicy


class LampTile(QFrame):
    selectionChanged = Signal(str, bool)  # device_id, selected

    def __init__(self, device_id: str, name: str, parent=None):
        super().__init__(parent)
        self.device_id = device_id
        self.setFrameShape(QFrame.StyledPanel)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)

        self.checkbox = QCheckBox()
        self.checkbox.setChecked(True)
        self.checkbox.toggled.connect(lambda checked: self.selectionChanged.emit(self.device_id, checked))
        layout.addWidget(self.checkbox)

        self.status_dot = QLabel("●")  # ●
        self.status_dot.setStyleSheet("color: #888; font-size: 14px;")
        self.status_dot.setFixedWidth(18)
        layout.addWidget(self.status_dot)

        self.name_label = QLabel(name)
        self.name_label.setMinimumWidth(90)
        layout.addWidget(self.name_label)

        self.ip_label = QLabel("")
        self.ip_label.setStyleSheet("color: #999;")
        self.ip_label.setMinimumWidth(100)
        layout.addWidget(self.ip_label)

        self.swatch = QFrame()
        self.swatch.setFixedSize(22, 16)
        self.swatch.setStyleSheet("background-color: #000; border: 1px solid #555;")
        layout.addWidget(self.swatch)

        self.status_label = QLabel("unknown")
        self.status_label.setMinimumWidth(70)
        layout.addWidget(self.status_label)

        self.latency_label = QLabel("- ms")
        self.latency_label.setMinimumWidth(60)
        layout.addWidget(self.latency_label)

        layout.addStretch(1)

    def set_name(self, name: str) -> None:
        self.name_label.setText(name)

    def set_ip(self, ip: str) -> None:
        self.ip_label.setText(ip)

    def set_selected(self, selected: bool) -> None:
        self.checkbox.blockSignals(True)
        self.checkbox.setChecked(selected)
        self.checkbox.blockSignals(False)

    def set_online(self, online: bool, error: str = "") -> None:
        if online:
            self.status_dot.setStyleSheet("color: #3ecf5e; font-size: 14px;")
            self.status_label.setText("Online")
            self.status_label.setToolTip("")
        else:
            self.status_dot.setStyleSheet("color: #d6493e; font-size: 14px;")
            self.status_label.setText("Offline")
            self.status_label.setToolTip(error or "No response")

    def set_color(self, r: int, g: int, b: int) -> None:
        self.swatch.setStyleSheet(f"background-color: rgb({r},{g},{b}); border: 1px solid #555;")

    def set_latency(self, latency_ms: "float | None") -> None:
        self.latency_label.setText(f"{latency_ms:.0f} ms" if latency_ms is not None else "- ms")
