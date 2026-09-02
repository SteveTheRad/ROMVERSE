from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from romverse.device.models import StorageInfo
from romverse.diagnostics.analyzer import DiagnosticAnalyzer
from romverse.diagnostics.history import DiagnosticHistoryStore
from romverse.ui.history_center import HistoryCenter
from romverse.ui.main_window import MainWindow

from .test_diagnostics import device


def test_health_timeline_surfaces_verified_and_rejected_evidence(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    store = DiagnosticHistoryStore(tmp_path)
    source = device()
    verified_path = store.save(DiagnosticAnalyzer().analyze(source), source)

    center = HistoryCenter(store)
    app.processEvents()
    assert "integrity verified" in center.evidence_status.text().casefold()
    assert "verified" in center.report_list.item(0).text().casefold()

    payload = json.loads(verified_path.read_text(encoding="utf-8"))
    payload["summary"] = "changed without a new digest"
    verified_path.write_text(json.dumps(payload), encoding="utf-8")
    center.refresh()
    app.processEvents()
    assert "rejected evidence" in center.evidence_status.text().casefold()
    assert "integrity mismatch" in center.evidence_status.text().casefold()
    assert center.report_list.count() == 0
    center.close()


def test_health_timeline_labels_legacy_snapshot_unverified(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    store = DiagnosticHistoryStore(tmp_path)
    source = device()
    path = store.save(DiagnosticAnalyzer().analyze(source), source)
    payload = json.loads(path.read_text(encoding="utf-8"))
    for key in (
        "snapshot_format",
        "snapshot_version",
        "snapshot_id",
        "snapshot_digest",
    ):
        payload.pop(key)
    path.write_text(json.dumps(payload), encoding="utf-8")

    center = HistoryCenter(store)
    app.processEvents()
    assert "legacy evidence" in center.evidence_status.text().casefold()
    assert "legacy" in center.report_list.item(0).text().casefold()
    center.close()


def test_health_timeline_reverifies_and_selects_exact_snapshot_context(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    store = DiagnosticHistoryStore(tmp_path)
    source = device()
    first_path = store.save(DiagnosticAnalyzer().analyze(source), source)
    second_path = store.save(
        DiagnosticAnalyzer().analyze(device(battery_percent=4)),
        device(battery_percent=4),
    )
    first_id = json.loads(first_path.read_text(encoding="utf-8"))["snapshot_id"]
    center = HistoryCenter(store)
    app.processEvents()

    assert center.open_snapshot(first_id)
    assert center.reports[center.report_list.currentRow()].snapshot_id == first_id

    payload = json.loads(second_path.read_text(encoding="utf-8"))
    second_id = payload["snapshot_id"]
    payload["summary"] = "tampered after activity was recorded"
    second_path.write_text(json.dumps(payload), encoding="utf-8")
    assert not center.open_snapshot(second_id)
    assert "REJECTED EVIDENCE" in center.evidence_status.text()
    center.close()


def test_health_timeline_routes_typed_history_to_exact_archives_guide(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    store = DiagnosticHistoryStore(tmp_path)
    source = device(storage=StorageInfo(percent_used=98))
    store.save(DiagnosticAnalyzer().analyze(source), source)
    center = HistoryCenter(store)
    articles: list[str] = []
    scans: list[bool] = []
    center.knowledge_article_requested.connect(articles.append)
    center.current_scan_requested.connect(lambda: scans.append(True))
    app.processEvents()

    assert "storage.capacity" in center.finding_guide_buttons
    assert center.report_list.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    center.finding_guide_buttons["storage.capacity"].click()
    center.current_scan_button.click()

    assert articles == ["device-storage-nearly-full"]
    assert scans == [True]
    assert "HISTORICAL SNAPSHOT" in next(
        label.text()
        for label in center.detail_content.findChildren(type(center.evidence_status))
        if "HISTORICAL SNAPSHOT" in label.text()
    )
    center.close()


def test_health_timeline_handoffs_reach_archives_and_current_optimizer(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(None, logo, tmp_path, app_icon_path=logo)
    snapshot = device(storage=StorageInfo(percent_used=98))
    try:
        window.diagnostics_center.set_devices([snapshot])
        window.diagnostics_center.save_button.click()
        window._navigate_route("health_timeline")
        app.processEvents()

        window.history_center.finding_guide_buttons["storage.capacity"].click()
        app.processEvents()

        assert window.stack.currentWidget() is window.knowledge_center
        assert window.knowledge_center.list.count() == 1
        assert window.knowledge_center.search.text() == "Android device storage is nearly full"
        assert "Very low free user-data space" in window.knowledge_center.detail.toPlainText()

        window._navigate_route("health_timeline")
        window.history_center.current_scan_button.click()
        app.processEvents()
        assert window.stack.currentWidget() is window.diagnostics_center
        assert window.diagnostics_center.current_report is not None
        assert not window.diagnostics_center.dashboard_handoff.isHidden()
        assert window.diagnostics_center.dashboard_handoff_title.text().startswith("Health Review")
        assert "NO NEW SCAN" in window.diagnostics_center.dashboard_handoff_detail.text()

        window._navigate_route("activity_center")
        window.activity_center.refresh()
        window.activity_center.search.setText("Health snapshot saved")
        app.processEvents()
        exact_id = window.activity_center.visible_events[0].context_id
        assert window.activity_center.open_source_button.text() == (
            "Open exact Health Timeline evidence"
        )
        window.activity_center.open_source_button.click()
        app.processEvents()
        assert window.stack.currentWidget() is window.history_center
        selected = window.history_center.reports[window.history_center.report_list.currentRow()]
        assert selected.snapshot_id == exact_id
    finally:
        window.companion_center.transport.close()
        window.close()
