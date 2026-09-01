from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QPushButton

from romverse.device.models import StorageInfo
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
    requested: list[str] = []
    center.repair_requested.connect(requested.append)

    center.set_devices([device(battery_percent=5)])
    app.processEvents()
    button = next(
        item
        for item in center.findChildren(QPushButton)
        if item.text() == "Open guided fix in Recovery Bay"
    )
    button.click()
    app.processEvents()

    assert requested == ["battery.low"]
    center.close()


def test_optimizer_handoff_preserves_storage_finding_identity(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    center = DiagnosticsCenter(
        DiagnosticAnalyzer(),
        DiagnosticHistoryStore(tmp_path),
    )
    requested: list[str] = []
    center.repair_requested.connect(requested.append)

    center.set_devices([device(storage=StorageInfo(percent_used=98))])
    app.processEvents()
    button = next(
        item
        for item in center.findChildren(QPushButton)
        if item.text() == "Open guided fix in Recovery Bay"
    )
    button.click()
    app.processEvents()

    assert requested == ["storage.capacity"]
    center.close()


def test_optimizer_reveals_exact_recovery_source_without_changing_evidence(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    center = DiagnosticsCenter(
        DiagnosticAnalyzer(),
        DiagnosticHistoryStore(tmp_path),
    )
    center.set_devices([device(storage=StorageInfo(percent_used=98))])
    report = center.current_report

    assert center.open_finding("storage.capacity")
    app.processEvents()

    card = center.finding_cards["storage.capacity"]
    assert card.property("diagnosticFocus") is True
    assert not card.source_context.isHidden()
    assert "RECOVERY BAY SOURCE" in card.source_context.text()
    assert "evidence view only" in center.saved_label.text()
    assert center.current_report is report

    assert not center.open_finding("unknown.future.rule")
    assert card.property("diagnosticFocus") is False
    assert card.source_context.isHidden()
    assert "refresh current evidence" in center.saved_label.text()
    assert center.current_report is report
    center.close()


def test_optimizer_can_search_archives_for_the_priority_finding(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    center = DiagnosticsCenter(
        DiagnosticAnalyzer(),
        DiagnosticHistoryStore(tmp_path),
    )
    requested: list[str] = []
    center.knowledge_article_requested.connect(requested.append)

    center.set_devices([device(battery_percent=5)])
    app.processEvents()
    button = next(
        item
        for item in center.findChildren(QPushButton)
        if item.text() == "Open verified fix in Archives"
    )
    button.click()
    app.processEvents()

    assert requested == ["device-battery-low"]
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
