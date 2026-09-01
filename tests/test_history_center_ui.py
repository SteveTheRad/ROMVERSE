from __future__ import annotations

import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from romverse.core.activity import ActivityStore
from romverse.diagnostics.analyzer import DiagnosticAnalyzer
from romverse.diagnostics.history import DiagnosticHistoryStore
from romverse.ui.history_center import HistoryCenter

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


def test_health_timeline_summarizes_real_activity_outcomes_for_beginners(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    activity = ActivityStore(tmp_path)
    activity.record(
        "optimizer",
        "Safe cleanup completed",
        "Two verified temporary files removed",
        outcome="success",
        source="Quantum Optimizer",
    )
    activity.record(
        "recovery",
        "Backup needs attention",
        "Local destination became unavailable",
        outcome="attention",
        source="Time Machine",
    )
    center = HistoryCenter(DiagnosticHistoryStore(tmp_path, activity), activity)
    app.processEvents()

    summary = center.activity_summary.text().casefold()
    assert "1 completed safely" in summary
    assert "1 need attention" in summary
    assert "latest: backup needs attention" in summary
    assert center.activity_list.item(0).text().startswith("!")
    center.close()
