from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from romverse.core.settings import ExperienceMode
from romverse.device.models import StorageInfo
from romverse.diagnostics.analyzer import DiagnosticAnalyzer
from romverse.diagnostics.history import DiagnosticHistoryStore
from romverse.ui.diagnostics_center import DiagnosticsCenter

from .test_diagnostics import device


def test_optimizer_routes_missing_runtime_to_platform_tools_instead_of_silent_scan(
    tmp_path,
) -> None:
    app = QApplication.instance() or QApplication([])
    center = DiagnosticsCenter(
        DiagnosticAnalyzer(),
        DiagnosticHistoryStore(tmp_path),
    )
    scans: list[bool] = []
    runtime_requests: list[bool] = []
    center.refresh_requested.connect(lambda: scans.append(True))
    center.runtime_tools_requested.connect(lambda: runtime_requests.append(True))
    center.set_runtime_available(False)

    center.refresh.click()
    app.processEvents()

    assert center.refresh.text() == "Resolve Platform Tools"
    assert center.device_name.text() == "Device Engine needs Platform Tools"
    assert "automatically retry" in center.summary.text()
    assert scans == []
    assert runtime_requests == [True]
    assert "opening Forge Arsenal" in center.saved_label.text()

    center.set_runtime_available(True)
    center.refresh.click()
    app.processEvents()
    assert scans == [True]
    assert runtime_requests == [True]
    center.close()


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


def test_recovery_cockpit_scans_local_archives_automatically(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    center = DiagnosticsCenter(
        DiagnosticAnalyzer(),
        DiagnosticHistoryStore(tmp_path),
    )

    center.set_devices([device(battery_percent=5)])
    app.processEvents()

    assert center.offline_report is not None
    assert center.offline_report.trigger == "diagnostic-report"
    assert center.offline_report.execution_authority == "none"
    assert center.flight_stages[0].property("state") == "complete"
    assert center.flight_stages[2].property("state") == "complete"
    assert center.flight_stages[3].property("state") == "active"
    assert center.action_plan_card is not None
    brain_eyebrow = center.action_plan_card.findChild(QLabel, "KnowledgeBrainEyebrow")
    assert brain_eyebrow is not None
    assert "AUTOMATIC LOCAL SCAN" in brain_eyebrow.text()
    center.close()


def test_recovery_cockpit_guided_mode_folds_evidence_and_expert_reveals_it(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    center = DiagnosticsCenter(
        DiagnosticAnalyzer(),
        DiagnosticHistoryStore(tmp_path),
    )
    center.set_devices([device(battery_percent=5)])
    app.processEvents()

    assert center.details_container is not None
    assert center.details_container.isHidden()

    center.set_experience_mode(ExperienceMode.EXPERT)
    app.processEvents()
    assert not center.details_container.isHidden()
    assert not center.utility_panel.isHidden()

    center.set_experience_mode(ExperienceMode.GUIDED)
    app.processEvents()
    assert center.details_container.isHidden()
    assert center.utility_panel.isHidden()
    center.close()


def test_recovery_cockpit_compares_fresh_evidence_after_guided_handoff(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    center = DiagnosticsCenter(
        DiagnosticAnalyzer(),
        DiagnosticHistoryStore(tmp_path),
    )
    center.set_devices([device(battery_percent=5)])
    center.mark_repair_handoff("battery.low")

    assert center.flight_stages[4].property("state") == "active"
    assert "will compare fresh evidence" in center.verification_detail.text()

    center.set_devices([device(battery_percent=80)])
    app.processEvents()

    assert center.verification_banner.property("state") == "complete"
    assert "no longer reports" in center.verification_title.text()
    assert "not proof" in center.verification_detail.text()
    assert center.flight_stages[4].property("state") == "complete"
    center.close()


def test_recovery_cockpit_remains_readable_without_horizontal_scrolling(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    center = DiagnosticsCenter(
        DiagnosticAnalyzer(),
        DiagnosticHistoryStore(tmp_path),
    )
    center.resize(900, 700)
    center.show()
    center.set_devices([device(battery_percent=5)])
    app.processEvents()

    assert center.body.horizontalScrollBar().maximum() == 0
    assert center.action_plan_card is not None
    assert center.action_plan_card.width() <= center.body.viewport().width()
    center.close()


def test_recovery_cockpit_rejects_outcome_comparison_from_a_different_phone(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    center = DiagnosticsCenter(
        DiagnosticAnalyzer(),
        DiagnosticHistoryStore(tmp_path),
    )
    center.set_devices([device(serial="PHONE-A", battery_percent=5)])
    center.mark_repair_handoff("battery.low")

    center.set_devices([device(serial="PHONE-B", battery_percent=80)])
    app.processEvents()

    assert center.verification_banner.property("state") == "attention"
    assert "original phone" in center.verification_title.text()
    assert "different device" in center.verification_detail.text()
    assert center._pending_verification_finding == "battery.low"
    center.close()
