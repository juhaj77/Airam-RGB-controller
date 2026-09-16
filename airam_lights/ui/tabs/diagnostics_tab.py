"""Diagnostics tab: rates, per-lamp connection/latency/command stats, and a
live log viewer. This is the "diagnostic mode" required for Phase 1/2 - the
same underlying data used to bring up the first bulb is shown here for all
of them, continuously, during normal operation."""
from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..controller import AppController

_COLUMNS = ["Lamp", "IP", "Online", "Bulb type", "Latency (ms)", "Sent", "Failed", "Skipped (unchanged)", "Last error"]


class DiagnosticsTab(QWidget):
    def __init__(self, controller: AppController, parent=None):
        super().__init__(parent)
        self.controller = controller

        root = QVBoxLayout(self)

        rates_box = QGroupBox("Update rates")
        rates_layout = QHBoxLayout(rates_box)
        self.analysis_rate_label = QLabel("Analysis (FFT): - Hz")
        self.visual_rate_label = QLabel("Visual: - Hz")
        self.audio_rate_label = QLabel("Audio callback: - Hz")
        self.mode_label = QLabel("Mode: -")
        for w in (self.analysis_rate_label, self.visual_rate_label, self.audio_rate_label, self.mode_label):
            rates_layout.addWidget(w)
        rates_layout.addStretch(1)
        root.addWidget(rates_box)

        table_box = QGroupBox("Lamps")
        table_layout = QVBoxLayout(table_box)
        self.table = QTableWidget(0, len(_COLUMNS))
        self.table.setHorizontalHeaderLabels(_COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table_layout.addWidget(self.table)
        root.addWidget(table_box, stretch=1)

        log_box = QGroupBox("Log")
        log_layout = QVBoxLayout(log_box)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(1000)
        log_layout.addWidget(self.log_view)
        root.addWidget(log_box, stretch=1)

        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._refresh)
        self._refresh_timer.start(1000)

        controller.logChanged.connect(self._refresh_log)
        self._refresh()
        self._refresh_log()

    def _refresh(self) -> None:
        engine = self.controller.engine
        self.analysis_rate_label.setText(f"Analysis (FFT): {engine.rate_counter_analysis.rate_hz():.1f} Hz")
        self.visual_rate_label.setText(f"Visual: {engine.rate_counter_visual.rate_hz():.1f} Hz")
        self.audio_rate_label.setText(f"Audio callback: {self.controller.audio.get_callback_rate_hz():.1f} Hz")
        self.mode_label.setText(f"Mode: {self.controller.config.color_mapping.mode}")

        devices = list(self.controller.lamp_manager.devices.values())
        self.table.setRowCount(len(devices))
        for row, dev in enumerate(devices):
            worker = self.controller.lamp_manager.workers.get(dev.config.id)
            values = [
                dev.config.name,
                dev.config.ip,
                "Yes" if dev.status.online else "No",
                str(dev.status.bulb_type or "-"),
                f"{dev.status.last_latency_ms:.0f}" if dev.status.last_latency_ms is not None else "-",
                str(worker.stats.commands_sent) if worker else "-",
                str(worker.stats.commands_failed) if worker else "-",
                str(worker.stats.commands_skipped_unchanged) if worker else "-",
                dev.status.last_error or "",
            ]
            for col, value in enumerate(values):
                self.table.setItem(row, col, QTableWidgetItem(value))

    def _refresh_log(self) -> None:
        lines = self.controller.log_buffer.get_recent(300)
        self.log_view.setPlainText("\n".join(lines))
        self.log_view.verticalScrollBar().setValue(self.log_view.verticalScrollBar().maximum())
