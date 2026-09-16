"""Add/Edit device dialog: manual IP + local Tuya credentials entry, plus a
'Test Connection' action that proves local control actually works before you
save the device - this is the Phase 1/2 "single bulb test page" folded into
the full app rather than a separate throwaway script.

Network calls run on a background thread; results come back via a Qt signal
(safe to emit cross-thread - PySide6 auto-queues the connection to the
dialog's own GUI thread).
"""
from __future__ import annotations

import threading

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from ...config.schema import DeviceConfig
from ...lamps.tuya_device import LampDevice


class DeviceDialog(QDialog):
    testFinished = Signal(bool, str, dict, object)  # online, error, raw_dps, latency_ms

    def __init__(self, device_config: "DeviceConfig | None" = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Lamp" if device_config else "Add Lamp")
        self.setMinimumWidth(420)
        self._existing_id = device_config.id if device_config else None

        form = QFormLayout()
        self.name_edit = QLineEdit(device_config.name if device_config else "Lamp")
        self.id_edit = QLineEdit(device_config.id if device_config else "")
        self.id_edit.setPlaceholderText("Tuya device id (gwId), from scan or cloud wizard")
        self.ip_edit = QLineEdit(device_config.ip if device_config else "")
        self.ip_edit.setPlaceholderText("192.168.1.xxx")
        self.key_edit = QLineEdit(device_config.local_key if device_config else "")
        self.key_edit.setEchoMode(QLineEdit.Password)
        self.key_edit.setPlaceholderText("local_key from setup wizard")
        self.version_combo = QComboBox()
        self.version_combo.addItems(["3.1", "3.3", "3.4", "3.5"])
        if device_config:
            idx = self.version_combo.findText(device_config.version)
            if idx >= 0:
                self.version_combo.setCurrentIndex(idx)
        else:
            self.version_combo.setCurrentText("3.3")

        form.addRow("Name:", self.name_edit)
        form.addRow("Device ID:", self.id_edit)
        form.addRow("IP address:", self.ip_edit)
        form.addRow("Local key:", self.key_edit)
        form.addRow("Protocol version:", self.version_combo)

        test_row = QHBoxLayout()
        self.test_button = QPushButton("Test Connection")
        self.test_button.clicked.connect(self._on_test)
        self.on_button = QPushButton("Turn On")
        self.on_button.clicked.connect(lambda: self._on_power(True))
        self.off_button = QPushButton("Turn Off")
        self.off_button.clicked.connect(lambda: self._on_power(False))
        self.rgb_test_button = QPushButton("Flash Red/Green/Blue")
        self.rgb_test_button.clicked.connect(self._on_rgb_test)
        test_row.addWidget(self.test_button)
        test_row.addWidget(self.on_button)
        test_row.addWidget(self.off_button)
        test_row.addWidget(self.rgb_test_button)

        self.result_box = QPlainTextEdit()
        self.result_box.setReadOnly(True)
        self.result_box.setMaximumHeight(140)
        self.result_box.setPlaceholderText(
            "Test results appear here: online state, raw datapoints (dps) reported by "
            "the bulb, detected bulb type, and command latency."
        )

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(test_row)
        layout.addWidget(QLabel("Diagnostics:"))
        layout.addWidget(self.result_box)
        layout.addWidget(buttons)

        self.testFinished.connect(self._show_test_result)

    def _build_temp_config(self) -> "DeviceConfig | None":
        if not self.ip_edit.text().strip() or not self.id_edit.text().strip():
            QMessageBox.warning(self, "Missing info", "Device ID and IP address are required to test the connection.")
            return None
        return DeviceConfig(
            id=self.id_edit.text().strip(),
            name=self.name_edit.text().strip() or "Lamp",
            ip=self.ip_edit.text().strip(),
            local_key=self.key_edit.text(),
            version=self.version_combo.currentText(),
        )

    def _on_test(self) -> None:
        cfg = self._build_temp_config()
        if cfg is None:
            return
        self.result_box.setPlainText("Testing...")

        def _run():
            dev = LampDevice(cfg)
            try:
                dev.refresh_status()
                self.testFinished.emit(dev.status.online, dev.status.last_error or "", dev.status.raw_dps, dev.status.last_latency_ms)
            except Exception as e:
                self.testFinished.emit(False, str(e), {}, None)

        threading.Thread(target=_run, daemon=True).start()

    def _show_test_result(self, online: bool, error: str, raw_dps: dict, latency_ms) -> None:
        lines = [f"Online: {online}"]
        if latency_ms is not None:
            lines.append(f"Latency: {latency_ms:.0f} ms")
        if error:
            lines.append(f"Error: {error}")
        if raw_dps:
            lines.append("Raw datapoints (dps) reported by the bulb:")
            for k, v in sorted(raw_dps.items()):
                lines.append(f"  {k}: {v}")
        self.result_box.setPlainText("\n".join(lines))

    def _on_power(self, on: bool) -> None:
        cfg = self._build_temp_config()
        if cfg is None:
            return

        def _run():
            dev = LampDevice(cfg)
            try:
                if on:
                    dev.turn_on(wait_for_ack=True)
                else:
                    dev.turn_off(wait_for_ack=True)
                self.testFinished.emit(True, "", {"power": on}, None)
            except Exception as e:
                self.testFinished.emit(False, str(e), {}, None)

        threading.Thread(target=_run, daemon=True).start()

    def _on_rgb_test(self) -> None:
        cfg = self._build_temp_config()
        if cfg is None:
            return

        def _run():
            import time

            dev = LampDevice(cfg)
            try:
                dev.ensure_colour_mode()
                for r, g, b in [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 255)]:
                    dev.set_color(r, g, b, wait_for_ack=True)
                    time.sleep(0.8)
                self.testFinished.emit(True, "", {"rgb_test": "complete"}, None)
            except Exception as e:
                self.testFinished.emit(False, str(e), {}, None)

        threading.Thread(target=_run, daemon=True).start()

    def get_device_config(self) -> DeviceConfig:
        return DeviceConfig(
            id=self.id_edit.text().strip(),
            name=self.name_edit.text().strip() or "Lamp",
            ip=self.ip_edit.text().strip(),
            local_key=self.key_edit.text(),
            version=self.version_combo.currentText(),
        )
