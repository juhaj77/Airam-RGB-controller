"""Main application window: tabbed UI wired to a single AppController."""
from __future__ import annotations

import logging

from PySide6.QtWidgets import QMainWindow, QMessageBox, QTabWidget

from .controller import AppController
from .tabs.band_mode_tab import BandModeTab
from .tabs.color_mapping_tab import ColorMappingTab
from .tabs.devices_tab import DevicesTab
from .tabs.diagnostics_tab import DiagnosticsTab
from .tabs.visualizer_tab import VisualizerTab

logger = logging.getLogger("airam_lights.ui")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Airam Music Lights")
        self.resize(1000, 750)

        self.controller = AppController()

        tabs = QTabWidget()
        self.setCentralWidget(tabs)

        tabs.addTab(VisualizerTab(self.controller), "Visualizer")
        tabs.addTab(DevicesTab(self.controller), "Devices && Setup")
        tabs.addTab(ColorMappingTab(self.controller), "Color Mapping")
        tabs.addTab(BandModeTab(self.controller), "8-Band && Per-Lamp")
        tabs.addTab(DiagnosticsTab(self.controller), "Diagnostics")

        self.controller.audioError.connect(self._on_audio_error)

    def _on_audio_error(self, message: str) -> None:
        QMessageBox.warning(self, "Audio capture error", message)

    def closeEvent(self, event) -> None:
        logger.info("Shutting down...")
        self.controller.shutdown()
        super().closeEvent(event)
