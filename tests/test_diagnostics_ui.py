from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QPushButton

from romverse.diagnostics.analyzer import DiagnosticAnalyzer
from romverse.diagnostics.history import DiagnosticHistoryStore
from romverse.ui.diagnostics_center import DiagnosticsCenter

from .test_diagnostics import device


def test_optimizer_routes_actionable_finding_to_guided_recovery(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    center = DiagnosticsCenter(
        DiagnosticAnalyzer(),
        DiagnosticHistoryStore(tmp_path),
    )
    requested: list[bool] = []
    center.repair_requested.connect(lambda: requested.append(True))

    center.set_devices([device(battery_percent=5)])
    app.processEvents()
    button = next(
        item
        for item in center.findChildren(QPushButton)
        if item.text() == "Open guided fix in Recovery Bay"
    )
    button.click()
    app.processEvents()

    assert requested == [True]
    center.close()


def test_optimizer_does_not_offer_repair_when_health_is_clear(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    center = DiagnosticsCenter(
        DiagnosticAnalyzer(),
        DiagnosticHistoryStore(tmp_path),
    )
    center.set_devices([device()])
    app.processEvents()

    assert all(
        item.text() != "Open guided fix in Recovery Bay"
        for item in center.findChildren(QPushButton)
    )
    center.close()


def test_optimizer_scan_shows_honest_indeterminate_progress(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    center = DiagnosticsCenter(
        DiagnosticAnalyzer(),
        DiagnosticHistoryStore(tmp_path),
    )
    center.show()
    app.processEvents()
    assert center.scan_status_row.isHidden()

    center.set_scanning(True)
    app.processEvents()

    assert not center.scan_status_row.isHidden()
    assert center.scan_status_row.height() == 34
    assert center.scan_status_label.text() == "SCAN"
    assert center.scan_progress.isVisible()
    assert center.scan_progress.width() == 68
    assert center.scan_progress.minimum() == 0
    assert center.scan_progress.maximum() == 0
    assert not center.scan_progress.isTextVisible()

    center.set_scanning(False)
    app.processEvents()
    assert center.scan_status_row.isHidden()
    assert not center.scan_progress.isVisible()
    center.close()
