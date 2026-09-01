from __future__ import annotations

import json
import os
import zipfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QFileDialog, QLabel

from romverse.core.activity import ActivityEvent, ActivityStore
from romverse.device.apk_install import ApkInstallRequest, create_install_plan
from romverse.diagnostics.analyzer import DiagnosticAnalyzer
from romverse.infrastructure.process import CommandResult
from romverse.repair.knowledge import knowledge_for
from romverse.repair.templates import RepairConcern
from romverse.ui.activity_center import (
    ActivityCenter,
    activity_source_route,
    filter_activity_events,
    summarize_activity,
)
from romverse.ui.main_window import MainWindow

from .test_diagnostics import device


def _event(
    event_id: str,
    category: str,
    title: str,
    detail: str,
    outcome: str,
    source: str,
) -> ActivityEvent:
    return ActivityEvent(
        event_id=event_id,
        recorded_at="2026-09-01T10:30:00+10:00",
        category=category,
        title=title,
        detail=detail,
        outcome=outcome,
        source=source,
    )


def test_activity_view_model_filters_summarizes_and_resolves_canonical_sources() -> None:
    events = (
        _event(
            "a",
            "diagnostics",
            "Health snapshot saved",
            "Score 92",
            "success",
            "System Scan",
        ),
        _event(
            "b",
            "repair",
            "Recovery needs attention",
            "ADB runtime missing",
            "attention",
            "Recovery Bay",
        ),
        _event(
            "c",
            "custom",
            "Local note",
            "No source page",
            "information",
            "Fixture",
        ),
    )

    summary = summarize_activity(events)
    assert (summary.total, summary.success, summary.attention, summary.information) == (3, 1, 1, 1)
    assert filter_activity_events(events, query="health 92") == (events[0],)
    assert filter_activity_events(events, category="repair", outcome="attention") == (events[1],)
    assert activity_source_route(events[0]) == "quantum_optimizer"
    assert activity_source_route(events[1]) == "recovery_bay"
    assert activity_source_route(events[2]) == ""


def test_activity_center_connects_filters_details_source_route_and_export(
    tmp_path, monkeypatch
) -> None:
    app = QApplication.instance() or QApplication([])
    store = ActivityStore(tmp_path)
    store.record(
        "diagnostics",
        "Health snapshot saved",
        "Phone evidence produced health score 92",
        outcome="success",
        source="System Scan",
    )
    store.record(
        "recovery",
        "Backup needs attention",
        "Local destination became unavailable",
        outcome="attention",
        source="Time Machine",
    )
    store.record(
        "rom-studio",
        "Project evidence reviewed",
        "Protected source remained unchanged",
        outcome="information",
        source="ROM Studio",
    )
    center = ActivityCenter(store)
    routes: list[str] = []
    center.route_requested.connect(routes.append)
    app.processEvents()
    try:
        assert center.metric_values["total"].text() == "3"
        assert center.metric_values["success"].text() == "1"
        assert center.metric_values["attention"].text() == "1"
        assert center.metric_values["information"].text() == "1"
        assert center.activity_list.count() == 3
        assert center.activity_list.accessibleName() == "Filtered ROMVERSE activity"

        center.resize(800, 600)
        center.show()
        app.processEvents()
        assert center.metrics_host.isHidden()
        assert not center.compact_summary.isHidden()
        assert center.subtitle.isHidden()
        assert "3 recorded" in center.compact_summary.text()

        center.outcome_filter.setCurrentIndex(center.outcome_filter.findData("attention"))
        app.processEvents()
        assert center.activity_list.count() == 1
        assert "Backup needs attention" in center.activity_list.item(0).text()

        center.outcome_filter.setCurrentIndex(center.outcome_filter.findData(""))
        center.search.setText("health score 92")
        app.processEvents()
        assert center.activity_list.count() == 1
        accessible = center.activity_list.item(0).data(Qt.ItemDataRole.AccessibleTextRole)
        assert accessible.startswith("Health snapshot saved. success. System Scan.")
        assert center.open_source_button.text() == "Open Quantum Optimizer"
        center.open_source_button.click()
        assert routes == ["quantum_optimizer"]

        destination = tmp_path / "activity-export.json"
        monkeypatch.setattr(
            QFileDialog,
            "getSaveFileName",
            lambda *_args, **_kwargs: (str(destination), "JSON (*.json)"),
        )
        center.export_button.click()
        payload = json.loads(destination.read_text(encoding="utf-8"))
        assert payload["privacy"] == "redacted"
        assert len(payload["events"]) == 3
        assert "Exported privacy-safe" in center.footer.text()
    finally:
        center.close()


def test_activity_center_preserves_and_surfaces_an_unreadable_ledger(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    ledger = tmp_path / "logs" / "activity-v1.json"
    ledger.parent.mkdir(parents=True)
    ledger.write_text("not json", encoding="utf-8")

    center = ActivityCenter(ActivityStore(tmp_path))
    app.processEvents()
    try:
        assert center.ledger_status.objectName() == "Danger"
        assert "ATTENTION" in center.ledger_status.text()
        assert center.metric_values["total"].text() == "0"
        assert "original data preserved" in center.compact_summary.text()
        assert not center.export_button.isEnabled()
        assert ledger.read_text(encoding="utf-8") == "not json"
    finally:
        center.close()


def test_activity_center_emits_exact_context_without_promoting_generic_entries(
    tmp_path,
) -> None:
    app = QApplication.instance() or QApplication([])
    store = ActivityStore(tmp_path)
    store.record(
        "rom-studio",
        "Project evidence reviewed",
        "Protected source remained unchanged",
        outcome="success",
        source="ROM Studio",
        source_route="rom_studio",
        context_type="rom-project",
        context_id="project-one-1234abcd",
    )
    center = ActivityCenter(store)
    exact: list[tuple[str, str, str]] = []
    generic: list[str] = []
    center.source_requested.connect(lambda *values: exact.append(values))
    center.route_requested.connect(generic.append)
    app.processEvents()
    try:
        assert center.open_source_button.text() == "Open exact ROM Studio evidence"
        assert any(
            "EXACT CONTEXT READY" in label.text()
            for label in center.detail_content.findChildren(QLabel)
        )
        center.open_source_button.click()
        assert exact == [("rom_studio", "rom-project", "project-one-1234abcd")]
        assert generic == []
    finally:
        center.close()


def test_activity_exact_project_handoff_restores_project_and_stale_context_stops(
    tmp_path,
) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(None, logo, tmp_path, app_icon_path=logo)
    project = window.rom_studio.store.create("Activity Source")
    window.activity_store.record(
        "rom-studio",
        "Project created",
        "Versioned project manifest preserved",
        outcome="success",
        source="ROM Studio",
        source_route="rom_studio",
        context_type="rom-project",
        context_id=project.project_id,
    )
    try:
        window._navigate_route("activity_center")
        window.activity_center.refresh()
        app.processEvents()
        window.activity_center.open_source_button.click()
        app.processEvents()

        assert window.stack.currentWidget() is window.rom_studio
        assert window.rom_studio.current_project is not None
        assert window.rom_studio.current_project.project_id == project.project_id

        window._navigate_route("activity_center")
        window._open_activity_source(
            "rom_studio",
            "rom-project",
            "missing-project-1234abcd",
        )
        assert window.stack.currentWidget() is window.activity_center
        assert "no longer available" in window.activity_center.footer.text()
        assert "No workspace or device state changed" in window.activity_center.footer.text()
    finally:
        window.companion_center.transport.close()
        window.close()


def test_activity_handoffs_connect_exact_backup_repair_and_apk_evidence(tmp_path) -> None:
    QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(None, logo, tmp_path, app_icon_path=logo)
    source_device = device(battery_percent=8)
    backup_plan = window.backup_center.plan_store.create(source_device)

    source = tmp_path / "activity-baseline.img"
    source.write_bytes(b"exact activity baseline" * 100)
    project = window.rom_studio.store.import_original(
        window.rom_studio.store.create("Activity evidence").project_id,
        source,
    )
    window.rom_studio.store.create_working_copy(project.project_id)
    snapshot = window.rom_studio.store.create_snapshot(project.project_id)

    assert window.repair_center.session_store is not None
    report = DiagnosticAnalyzer().analyze(source_device)
    repair_session = window.repair_center.session_store.start(
        RepairConcern.BATTERY_HEAT,
        source_device,
        report,
        knowledge_for(RepairConcern.BATTERY_HEAT).recommended_steps,
    )

    apk = tmp_path / "activity.apk"
    with zipfile.ZipFile(apk, "w") as archive:
        archive.writestr("AndroidManifest.xml", b"manifest")
        archive.writestr("classes.dex", b"dex\n035\0")
    apk_plan = create_install_plan(
        ApkInstallRequest(
            str(apk),
            source_device.serial,
            battery_percent=90,
            device_free_bytes=1024**3,
        ),
        "privacy-safe-target",
    )
    apk_receipt = window.apk_installer.receipts.write_install(
        apk_plan,
        CommandResult(("adb",), 1, "", "INSTALL_FAILED_INVALID_APK"),
        False,
    )

    try:
        window._open_activity_source("time_machine", "backup-plan", backup_plan.plan_id)
        assert window.stack.currentWidget() is window.backup_center
        assert backup_plan.plan_id in window.backup_center.plan_context_detail.text()

        window._open_activity_source(
            "time_machine",
            "time-machine-snapshot",
            f"{project.project_id}.{snapshot.snapshot_id}",
        )
        assert window.stack.currentWidget() is window.backup_center
        assert snapshot.snapshot_id in window.backup_center.local_result.text()

        window._open_activity_source(
            "recovery_bay",
            "repair-session",
            repair_session.session_id,
        )
        assert window.stack.currentWidget() is window.repair_center
        assert repair_session.session_id in window.repair_center.session_context_detail.text()

        window._open_activity_source(
            "app_launchpad",
            "apk-install-receipt",
            apk_receipt.receipt_id,
        )
        assert window.stack.currentWidget() is window.apk_installer
        assert apk_receipt.receipt_id in window.apk_installer.receipt_context_detail.text()
        assert window.apk_installer.current_plan is None
        assert not window.apk_installer.install_button.isEnabled()
    finally:
        window.companion_center.transport.close()
        window.close()


def test_activity_handoff_restores_exact_galaxy_topic_and_stops_when_missing(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(None, logo, tmp_path, app_icon_path=logo)
    topic = window.galaxy_center.store.create_post(
        "Galaxy activity source",
        "This private topic must reopen exactly.",
    )
    window.activity_store.record(
        "community",
        "Local Galaxy topic created",
        "Private offline evidence",
        outcome="success",
        source="ROMVERSE Galaxy",
        source_route="galaxy",
        context_type="galaxy-topic",
        context_id=topic.post_id,
    )
    try:
        window._navigate_route("activity_center")
        window.activity_center.refresh()
        app.processEvents()
        assert window.activity_center.open_source_button.text() == (
            "Open exact ROMVERSE Galaxy evidence"
        )
        window.activity_center.open_source_button.click()
        app.processEvents()

        assert window.stack.currentWidget() is window.galaxy_center
        assert window.galaxy_center.current_post_id == topic.post_id
        assert window.galaxy_center.topic_title.text() == "Galaxy activity source"
        assert "Nothing was published" in window.galaxy_center.status.text()

        window.galaxy_center.store.delete_post(topic.post_id)
        window._navigate_route("activity_center")
        window._open_activity_source("galaxy", "galaxy-topic", topic.post_id)
        assert window.stack.currentWidget() is window.activity_center
        assert "missing or failed integrity" in window.activity_center.footer.text()
        assert "No workspace or device state changed" in window.activity_center.footer.text()
    finally:
        window.companion_center.transport.close()
        window.close()
