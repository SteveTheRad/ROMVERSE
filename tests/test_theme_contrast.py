from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QScrollArea, QSpinBox, QVBoxLayout, QWidget

from romverse.ui.theme import STYLESHEET, apply_dark_palette


def test_shared_theme_overrides_a_light_host_palette_for_plain_and_scroll_surfaces() -> None:
    app = QApplication.instance() or QApplication([])
    previous_palette = QPalette(app.palette())
    previous_stylesheet = app.styleSheet()
    light_palette = QPalette(previous_palette)
    for group in (
        QPalette.ColorGroup.Active,
        QPalette.ColorGroup.Inactive,
        QPalette.ColorGroup.Disabled,
    ):
        light_palette.setColor(group, QPalette.ColorRole.Window, QColor("#ffffff"))
        light_palette.setColor(group, QPalette.ColorRole.Base, QColor("#ffffff"))
        light_palette.setColor(group, QPalette.ColorRole.WindowText, QColor("#ffffff"))
        light_palette.setColor(group, QPalette.ColorRole.Text, QColor("#ffffff"))
    app.setStyle("Fusion")
    app.setPalette(light_palette)
    apply_dark_palette(app)
    app.setStyleSheet(STYLESHEET)

    root = QWidget()
    layout = QVBoxLayout(root)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setWidget(QWidget())
    layout.addWidget(scroll)
    spin = QSpinBox()
    spin.setValue(8)
    layout.addWidget(spin)
    root.resize(500, 320)
    root.show()
    app.processEvents()
    try:
        root_pixel = root.grab().toImage().pixelColor(4, 4)
        viewport_pixel = scroll.viewport().grab().toImage().pixelColor(20, 20)
        spin_pixel = spin.grab().toImage().pixelColor(spin.width() // 2, spin.height() // 2)
        assert root_pixel.lightness() < 40
        assert viewport_pixel.lightness() < 40
        assert spin_pixel.lightness() < 60
        assert root.palette().color(QPalette.ColorRole.WindowText).lightness() > 160
    finally:
        root.close()
        app.setStyleSheet(previous_stylesheet)
        app.setPalette(previous_palette)
