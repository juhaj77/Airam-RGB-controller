"""Manual Color tab: pick a static color from a color picker and apply it to
whichever lamps are currently selected (checkboxes in the Devices & Setup
tab - the same lamp list/selection state is shared across both apps)."""
from __future__ import annotations

import logging
import threading

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...color.models import Color
from ..manual_controller import ManualController

logger = logging.getLogger("airam_lights.ui.manual")


class ManualColorTab(QWidget):
    def __init__(self, controller: ManualController, parent=None):
        super().__init__(parent)
        self.controller = controller
        self._current_qcolor = QColor(70, 130, 255)

        root = QVBoxLayout(self)

        box = QGroupBox("Set a static color for the selected lamps")
        box_layout = QVBoxLayout(box)
        box_layout.addWidget(
            QLabel(
                "Select which lamps participate in the Devices & Setup tab (checkboxes), then pick a "
                "color here and apply it. This sends one fixed color - no music, no animation, unless "
                "you also enable the Chase effect on the Chase tab."
            )
        )

        preview_row = QHBoxLayout()
        preview_row.addWidget(QLabel("Color:"))
        self.swatch = QFrame()
        self.swatch.setFixedSize(56, 32)
        self.swatch.setFrameShape(QFrame.Box)
        self._update_swatch()
        preview_row.addWidget(self.swatch)

        pick_btn = QPushButton("Pick Color...")
        pick_btn.clicked.connect(self._on_pick_color)
        preview_row.addWidget(pick_btn)

        apply_btn = QPushButton("Apply to Selected")
        apply_btn.clicked.connect(self._on_apply)
        preview_row.addWidget(apply_btn)
        preview_row.addStretch(1)
        box_layout.addLayout(preview_row)

        power_row = QHBoxLayout()
        on_btn = QPushButton("Turn On + Apply Color")
        on_btn.clicked.connect(self._on_turn_on)
        off_btn = QPushButton("Turn Off Selected")
        off_btn.clicked.connect(self._on_turn_off)
        power_row.addWidget(on_btn)
        power_row.addWidget(off_btn)
        power_row.addStretch(1)
        box_layout.addLayout(power_row)

        root.addWidget(box)
        root.addStretch(1)

    def _update_swatch(self) -> None:
        c = self._current_qcolor
        self.swatch.setStyleSheet(f"background-color: rgb({c.red()},{c.green()},{c.blue()}); border: 1px solid #555;")

    def _current_color(self) -> Color:
        c = self._current_qcolor
        return Color(c.red() / 255.0, c.green() / 255.0, c.blue() / 255.0)

    def _selected_or_warn(self) -> "list[str] | None":
        ids = list(self.controller.lamp_manager.selected_device_ids())
        if not ids:
            QMessageBox.information(self, "No selection", "Select at least one lamp in the Devices & Setup tab first.")
            return None
        return ids

    def _on_pick_color(self) -> None:
        color = QColorDialog.getColor(self._current_qcolor, self, "Pick a color")
        if color.isValid():
            self._current_qcolor = color
            self._update_swatch()

    def _on_apply(self) -> None:
        if self._selected_or_warn() is None:
            return
        self.controller.set_color_for_selected(self._current_color())

    def _on_turn_on(self) -> None:
        ids = self._selected_or_warn()
        if ids is None:
            return

        def _run():
            for device_id in ids:
                dev = self.controller.lamp_manager.devices.get(device_id)
                if dev is None:
                    continue
                try:
                    dev.ensure_colour_mode()
                    dev.turn_on(wait_for_ack=False)
                except Exception as e:
                    logger.warning("Failed to turn on '%s': %s", device_id, e)

        threading.Thread(target=_run, daemon=True).start()
        self.controller.set_color_for_selected(self._current_color())

    def _on_turn_off(self) -> None:
        ids = self._selected_or_warn()
        if ids is None:
            return

        def _run():
            for device_id in ids:
                dev = self.controller.lamp_manager.devices.get(device_id)
                if dev is None:
                    continue
                try:
                    dev.turn_off(wait_for_ack=False)
                except Exception as e:
                    logger.warning("Failed to turn off '%s': %s", device_id, e)

        threading.Thread(target=_run, daemon=True).start()
        self.controller.set_black_for_selected()
