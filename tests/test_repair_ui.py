from __future__ import annotations

import os
from dataclasses import replace
from importlib.resources import files

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QMessageBox, QPushButton

from romverse.core.activity import ActivityStore
from romverse.device.models import DeviceState, StorageInfo
from romverse.device_packs.registry import DevicePackRegistry
from romverse.diagnostics.analyzer import DiagnosticAnalyzer
from romverse.guardian.approval import ApprovalStore
from romverse.guardian.gateway import ExecutionGateway
from romverse.guardian.planning import GuardianPreflight
from romverse.guardian.policy import GuardianPolicy
from romverse.infrastructure.process import CommandResult
from romverse.intelligence.online_remediation import (
    ErrorFingerprint,
    OnlineFixCandidate,
    OnlineRemediationService,
    SourceAuthority,
)
from romverse.knowledge.lookup import OfflineKnowledgeService
from romverse.knowledge.models import KnowledgeFailure
from romverse.repair.autopilot import (
    RecoveryIncidentState,
    RecoveryRouteKind,
    RecoveryTrigger,
)
from romverse.repair.host import AdbHostRepairReceiptStore, AdbHostRepairService
from romverse.repair.templates import RepairAssessmentTemplates, RepairConcern
from romverse.ui.repair_center import RepairCenter

from .test_diagnostics import device


class UiHostRepairRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def run(self, args, timeout=10, cwd=None):
        call = tuple(str(part) for part in args)
        self.calls.append(call)
        return CommandResult(call, 0, "List of devices attached\n", "")


def host_repair_service(tmp_path):
    adb = tmp_path / "adb"
    adb.write_bytes(b"verified adb UI fixture")
    adb.chmod(0o755)
    runner = UiHostRepairRunner()
    service = AdbHostRepairService(
        adb,
        ExecutionGateway(GuardianPolicy(tmp_path), runner),
        ApprovalStore(tmp_path),
        AdbHostRepairReceiptStore(tmp_path),
    )
    return service, runner


class OfficialAdbResearchProvider:
    def search(self, _fingerprint):
        return (
            OnlineFixCandidate(
                "official.adb.recovery",
                SourceAuthority.OFFICIAL,
                "Android Debug Bridge documentation",
                "https://developer.android.com/tools/adb",
                "Verify host Platform Tools, recover the ADB daemon, and rerun the exact connection check.",
                ("adb", "offline"),
                "adb-host-recovery",
                "refresh-adb-evidence",
                90,
            ),
        )


class MultiSourceResearchProvider:
    def search(self, _fingerprint):
        return (
            OnlineFixCandidate(
                "official.samsung.update",
                SourceAuthority.OFFICIAL,
                "Samsung official update guidance",
                "https://www.samsung.com/us/support/answer/ANS10002027/",
                "Check the exact Galaxy model and current update state.",
                confidence=90,
            ),
            OnlineFixCandidate(
                "maintainer.android.update",
                SourceAuthority.MAINTAINER,
                "Maintainer update diagnosis",
                "https://github.com/android/platform_system_update_engine/issues/1",
                "Compare the exact update error with the maintained implementation.",
                confidence=78,
            ),
            OnlineFixCandidate(
                "community.android.update",
                SourceAuthority.COMMUNITY,
                "Community update report",
                "https://xdaforums.com/t/example-update-report.1234567/",
                "One device owner reported the same symptom.",
                confidence=68,
            ),
        )


class OfficialPlatformToolsProvider:
    def search(self, _fingerprint):
        return (
            OnlineFixCandidate(
                "android.platform-tools",
                SourceAuthority.OFFICIAL,
                "SDK Platform Tools release notes",
                "https://developer.android.com/tools/releases/platform-tools",
                "Verify the exact ADB and Fastboot package before repeating the host check.",
                ("platform tools", "command not found"),
                "android.platform-tools",
                "verify-platform-tools",
                92,
            ),
        )


def test_guided_repair_ui_saves_checkpoints_then_requires_fresh_scan(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    activity = ActivityStore(tmp_path)
    center = RepairCenter(
        DiagnosticAnalyzer(),
        RepairAssessmentTemplates(),
        GuardianPreflight(),
        tmp_path,
        activity,
    )
    center.set_devices([device(battery_percent=8)])
    center._start_session()
    app.processEvents()
    assert center.active_session is not None
    assert center.active_session.status == "active"
    assert center.active_session.archive_article_keys == ("device-battery-low",)
    session_id = center.active_session.session_id
    started = activity.list_recent()[0]
    assert started.context_type == "repair-session"
    assert started.context_id == session_id

    for check in center.session_checks:
        check.setChecked(True)
    center._save_session_progress()
    app.processEvents()
    assert center.active_session is not None
    assert center.active_session.status == "ready_for_verification"
    assert center.active_session.verification_summary == ""

    requested: list[bool] = []
    center.verification_scan_requested.connect(lambda: requested.append(True))
    center._request_verification()
    assert requested == [True]
    center.set_devices([device(battery_percent=80)])
    app.processEvents()
    assert center.active_session is not None
    assert center.active_session.status == "verified"
    assert "improved" in center.active_session.verification_summary
    verified = activity.list_recent()[0]
    assert verified.context_type == "repair-session"
    assert verified.context_id == session_id
    assert center.open_session(session_id)
    assert center.session_context_row.isVisibleTo(center)
    assert session_id in center.session_context_detail.text()
    assert "no repair" in center.session_context_detail.text().casefold()
    center.close()


def test_recovery_bay_prefers_authorized_device_in_multi_device_state(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    center = RepairCenter(
        DiagnosticAnalyzer(),
        RepairAssessmentTemplates(),
        GuardianPreflight(),
        tmp_path,
        ActivityStore(tmp_path),
    )
    center.set_devices(
        [
            device(serial="waiting", state=DeviceState.UNAUTHORIZED),
            device(serial="ready", state=DeviceState.DEVICE),
        ]
    )
    app.processEvents()

    assert center.device_selector.currentIndex() == 1
    assert center.current_device is not None
    assert center.current_device.serial == "ready"
    assert center.session_button.isEnabled()
    assert center.execute_button.isEnabled()
    assert "read-only diagnostics" in center.execute_button.text().casefold()
    center.close()


def test_recovery_bay_opens_exact_diagnostic_context_without_starting_action(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    center = RepairCenter(
        DiagnosticAnalyzer(),
        RepairAssessmentTemplates(),
        GuardianPreflight(),
        tmp_path,
        ActivityStore(tmp_path),
    )
    center.set_devices([device(storage=StorageInfo(percent_used=98))])
    center.online_service = object()

    opened = center.open_diagnostic_finding("storage.capacity")
    app.processEvents()

    assert opened
    assert center.current_concern is RepairConcern.STORAGE
    assert center.concern_selector.currentData() == RepairConcern.STORAGE.value
    assert not center.diagnostic_context.isHidden()
    assert "STORAGE.CAPACITY" in center.diagnostic_context.text()
    assert "NO ACTION STARTED" in center.diagnostic_context.text()
    assert "Storage or update-space problem" in center.plan_title.text()
    assert center.active_session is None
    assert center.host_repair_worker is None
    assert center.online_worker is None
    assert center.intelligence_card.isHidden()
    requested: list[str] = []
    center.diagnostic_requested.connect(requested.append)
    center.diagnostic_source_button.click()
    app.processEvents()
    assert requested == ["storage.capacity"]

    center.concern_selector.setCurrentIndex(
        center.concern_selector.findData(RepairConcern.NETWORK.value)
    )
    app.processEvents()
    assert center.diagnostic_context.isHidden()
    assert center.diagnostic_context_row.isHidden()
    assert center.current_concern is RepairConcern.NETWORK
    center.close()


def test_recovery_bay_rejects_unknown_or_stale_diagnostic_handoff(tmp_path) -> None:
    QApplication.instance() or QApplication([])
    center = RepairCenter(
        DiagnosticAnalyzer(),
        RepairAssessmentTemplates(),
        GuardianPreflight(),
        tmp_path,
        ActivityStore(tmp_path),
    )
    center.set_devices([device()])
    original_concern = center.current_concern

    assert not center.open_diagnostic_finding("storage.capacity")
    assert not center.open_diagnostic_finding("unknown.future.rule")
    assert center.current_concern is original_concern
    assert center.diagnostic_context.isHidden()
    assert center.active_session is None
    assert center.host_repair_worker is None
    center.close()


def test_recovery_bay_general_command_deck_intake_clears_exact_source(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    center = RepairCenter(
        DiagnosticAnalyzer(),
        RepairAssessmentTemplates(),
        GuardianPreflight(),
        tmp_path,
        ActivityStore(tmp_path),
    )
    center.set_devices([device(storage=StorageInfo(percent_used=98))])
    assert center.open_diagnostic_finding("storage.capacity")

    center.open_general_assessment()
    app.processEvents()

    assert not center.diagnostic_context_row.isHidden()
    assert "FROM COMMAND DECK" in center.diagnostic_context.text()
    assert "NO CURRENT ACTIONABLE DIAGNOSTIC" in center.diagnostic_context.text()
    assert "NO ACTION STARTED" in center.diagnostic_context.text()
    assert center.diagnostic_source_button.isHidden()
    assert center._diagnostic_context_id == ""
    assert center.active_session is None
    assert center.host_repair_worker is None
    assert center.online_worker is None
    center.close()


def test_recovery_bay_fresh_diagnostics_is_a_real_scan_action(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    center = RepairCenter(
        DiagnosticAnalyzer(),
        RepairAssessmentTemplates(),
        GuardianPreflight(),
        tmp_path,
        ActivityStore(tmp_path),
    )
    center.set_devices([device()])
    requested: list[bool] = []
    center.verification_scan_requested.connect(lambda: requested.append(True))

    center.execute_button.click()
    app.processEvents()

    assert requested == [True]
    assert "fresh read-only" in center.digest.text().casefold()
    center.close()


def test_recovery_bay_searches_local_archives_without_starting_a_repair(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    center = RepairCenter(
        DiagnosticAnalyzer(),
        RepairAssessmentTemplates(),
        GuardianPreflight(),
        tmp_path,
        ActivityStore(tmp_path),
    )
    queries: list[str] = []
    center.knowledge_requested.connect(queries.append)
    center.symptom_input.setText("  INSTALL_FAILED_VERSION_DOWNGRADE\x00  ")

    center.archives_button.click()
    app.processEvents()

    assert queries == ["INSTALL_FAILED_VERSION_DOWNGRADE"]
    assert center.active_session is None
    assert center.host_repair_worker is None
    center.close()


def test_recovery_bay_automatically_ranks_structured_offline_evidence(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    center = RepairCenter(
        DiagnosticAnalyzer(),
        RepairAssessmentTemplates(),
        GuardianPreflight(),
        tmp_path,
        ActivityStore(tmp_path),
        offline_service=OfflineKnowledgeService(tmp_path),
    )
    center.symptom_input.setText("adb: error: more than one device/emulator")
    center.set_devices([device()])
    app.processEvents()

    assert center.offline_report is not None
    assert center.offline_report.trigger == "recovery-bay"
    assert center.offline_report.execution_authority == "none"
    assert center.offline_report.matches[0].record.record_id == "catalog.adb-multiple-targets"
    labels = "\n".join(label.text() for label in center.findChildren(QLabel))
    assert "OFFLINE ARCHIVES BRAIN" in labels
    assert "AUTOMATIC EVIDENCE MATCH" in labels
    assert "EXECUTION AUTHORITY: NONE" in labels
    assert "PHONE CHANGES: NONE" in labels
    assert center._report_payload is not None
    offline_payload = center._report_payload["offline_knowledge"]
    assert offline_payload["matches"][0]["record_id"] == "catalog.adb-multiple-targets"
    queries: list[str] = []
    center.knowledge_requested.connect(queries.append)
    review = next(
        button
        for button in center.findChildren(QPushButton)
        if button.text() == "Review all matching offline evidence"
    )
    review.click()
    assert queries == ["adb: error: more than one device/emulator"]
    assert center.active_session is None
    center.close()


def test_recovery_bay_diagnoses_device_discovery_failure_offline_without_action(
    tmp_path,
) -> None:
    app = QApplication.instance() or QApplication([])
    center = RepairCenter(
        DiagnosticAnalyzer(),
        RepairAssessmentTemplates(),
        GuardianPreflight(),
        tmp_path,
        ActivityStore(tmp_path),
        offline_service=OfflineKnowledgeService(tmp_path),
    )
    queries: list[str] = []
    center.knowledge_requested.connect(queries.append)

    center.show_error("adb: error: more than one device/emulator\x00")
    app.processEvents()

    assert center.offline_report is not None
    assert center.offline_report.trigger == "device-discovery-failure"
    assert center.offline_report.execution_authority == "none"
    assert center.offline_report.matches[0].record.record_id == "catalog.adb-multiple-targets"
    labels = "\n".join(label.text() for label in center.findChildren(QLabel))
    assert "OFFLINE ARCHIVES BRAIN" in labels
    assert "ADB error: more than one device or emulator" in labels
    assert "EXECUTION AUTHORITY: NONE" in labels
    assert center.host_repair_plan is None
    assert center.host_repair_worker is None
    assert center._report_payload is None

    review = next(
        button
        for button in center.findChildren(QPushButton)
        if button.text() == "Review all matching offline evidence"
    )
    review.click()
    assert queries == ["adb: error: more than one device/emulator"]
    assert center.host_repair_worker is None
    center.close()


def test_recovery_bay_advisor_opens_exact_symptom_fix_and_exports_reason(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    center = RepairCenter(
        DiagnosticAnalyzer(),
        RepairAssessmentTemplates(),
        GuardianPreflight(),
        tmp_path,
        ActivityStore(tmp_path),
    )
    requested: list[str] = []
    center.knowledge_article_requested.connect(requested.append)
    center.symptom_input.setText("INSTALL_FAILED_VERSION_DOWNGRADE")
    center.set_devices([device()])
    app.processEvents()

    button = next(
        item
        for item in center.findChildren(QPushButton)
        if item.text() == "Open verified Archives guide"
    )
    button.click()
    app.processEvents()

    assert requested == ["apk-version-downgrade"]
    assert "INSTALL_FAILED_VERSION_DOWNGRADE" in button.accessibleName()
    assert center._report_payload is not None
    recommendations = center._report_payload["archive_recommendations"]
    assert isinstance(recommendations, list)
    assert recommendations[0]["article_key"] == "apk-version-downgrade"
    assert recommendations[0]["source_authority"] == "AOSP SOURCE"
    assert recommendations[0]["source_url"].startswith("https://android.googlesource.com/")
    assert center.active_session is None
    assert center.host_repair_worker is None
    center.close()


def test_recovery_bay_keeps_disabled_online_research_compact_but_discoverable(
    tmp_path,
) -> None:
    app = QApplication.instance() or QApplication([])
    center = RepairCenter(
        DiagnosticAnalyzer(),
        RepairAssessmentTemplates(),
        GuardianPreflight(),
        tmp_path,
        ActivityStore(tmp_path),
    )
    center.set_devices([device(battery_percent=8)])
    app.processEvents()

    assert not center.intelligence_card.isHidden()
    assert center.intelligence_details.isHidden()
    assert "LOCAL ADVISOR ACTIVE" in center.intelligence_status.text()
    assert center.intelligence_toggle.text() == "SHOW RESEARCH DETAILS"
    assert center.intelligence_toggle.accessibleName()
    assert center.intelligence_status.accessibleName()

    center.intelligence_toggle.click()
    app.processEvents()

    assert not center.intelligence_details.isHidden()
    assert center.intelligence_toggle.text() == "HIDE RESEARCH DETAILS"
    assert "Enable verified online diagnostics" in center.intelligence_detail.text()
    center.close()


def test_recovery_bay_resolves_missing_adb_runtime_from_blocked_state(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    center = RepairCenter(
        DiagnosticAnalyzer(),
        RepairAssessmentTemplates(),
        GuardianPreflight(),
        tmp_path,
        ActivityStore(tmp_path),
    )
    service, _runner = host_repair_service(tmp_path)
    requested = []
    center.runtime_tools_requested.connect(
        lambda: (
            requested.append(True),
            center.set_host_repair_service(service),
        )
    )

    assert not center.resolve_runtime_button.isHidden()
    center.resolve_runtime_button.click()
    app.processEvents()

    assert requested == [True]
    assert center.host_repair_service is service
    assert center.resolve_runtime_button.isHidden()
    assert "still need attention" not in center.plan_title.text().casefold()
    center.close()


def test_recovery_bay_shows_source_backed_oem_context(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
    center = RepairCenter(
        DiagnosticAnalyzer(),
        RepairAssessmentTemplates(),
        GuardianPreflight(),
        tmp_path,
        ActivityStore(tmp_path),
        registry,
    )

    center.set_devices([device(manufacturer="Google", model="Pixel 9 Pro")])
    app.processEvents()

    labels = [label.text() for label in center.findChildren(QLabel)]
    assert any("Source-backed OEM context" in text and "Google Pixel" in text for text in labels)
    assert any("Google Pixel factory images" in text for text in labels)
    assert center._report_payload is not None
    pack = center._report_payload["device_pack"]
    assert isinstance(pack, dict)
    assert pack["pack_id"] == "google.pixel"
    assert pack["execution_authority"] == "none"
    center.close()


def test_recovery_bay_offers_exact_host_only_adb_repair_and_rescans(tmp_path, monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    service, runner = host_repair_service(tmp_path)
    center = RepairCenter(
        DiagnosticAnalyzer(),
        RepairAssessmentTemplates(),
        GuardianPreflight(),
        tmp_path,
        ActivityStore(tmp_path),
        host_repair_service=service,
    )
    center.set_devices([device(state=DeviceState.OFFLINE)])
    center.concern_selector.setCurrentIndex(
        center.concern_selector.findData(RepairConcern.USB_ADB.value)
    )
    app.processEvents()

    assert center.host_repair_plan is not None
    assert center.host_repair_button is not None
    assert center.host_repair_button.isEnabled()
    assert center.layout().indexOf(center.host_action_card) < center.layout().indexOf(center.body)
    assert not center.host_action_card.isHidden()
    assert center.host_repair_plan.phone_changed is False
    assert center.host_repair_plan.bootloader_relock == "never"

    requested: list[bool] = []
    center.verification_scan_requested.connect(lambda: requested.append(True))
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(
        "romverse.ui.repair_center.start_background",
        lambda worker: worker.execute(),
    )
    center.host_repair_button.click()
    app.processEvents()

    assert [call[1:] for call in runner.calls] == [
        ("kill-server",),
        ("start-server",),
        ("devices", "-l"),
    ]
    assert all("-s" not in call for call in runner.calls)
    assert requested == [True]
    assert "rescan" in center.digest.text().casefold()
    assert service.receipts.load_latest().valid
    center.close()


def test_recovery_autopilot_cockpit_opens_from_evidence_and_survives_disconnect(
    tmp_path,
) -> None:
    app = QApplication.instance() or QApplication([])
    center = RepairCenter(
        DiagnosticAnalyzer(),
        RepairAssessmentTemplates(),
        GuardianPreflight(),
        tmp_path,
        ActivityStore(tmp_path),
    )
    center.set_devices([device(state=DeviceState.UNAUTHORIZED)])

    created = center.open_recovery_incident(
        RecoveryTrigger.DEVICE_MODE,
        message="ADB authorization is required after reconnect",
    )
    app.processEvents()

    assert created
    assert center.autopilot_incident is not None
    assert center.autopilot_incident.state is RecoveryIncidentState.STABILIZING
    assert center.autopilot_card.isVisibleTo(center)
    assert "ADB UNAUTHORIZED" in center.autopilot_title.text()
    assert center.autopilot_route_buttons
    assert "RECOVERED REQUIRES FRESH BOOT + RECONNECT PROOF" in (
        center.autopilot_boundary.text()
    )

    center.set_devices([])
    app.processEvents()

    assert center.autopilot_incident is not None
    assert center.autopilot_incident.mode == "disconnected"
    assert center.autopilot_incident.state is RecoveryIncidentState.EMERGENCY
    assert not center.autopilot_incident.repaired
    assert "EMERGENCY" in center.autopilot_badge.text()
    center.close()


def test_generic_recovery_refresh_waits_for_sealed_phone_and_reuses_incident(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    center = RepairCenter(
        DiagnosticAnalyzer(),
        RepairAssessmentTemplates(),
        GuardianPreflight(),
        tmp_path,
        ActivityStore(tmp_path),
    )
    original = device(serial="SEALED-ORIGINAL-PHONE")
    other = replace(original, serial="SAME-MODEL-OTHER-PHONE")
    expected = center.autopilot_service.privacy.pseudonym(original.serial)

    assert center.open_recovery_incident(
        RecoveryTrigger.FLASH_FAILURE,
        project_id="interrupted-project",
        message="Wait for the phone involved in the interrupted installation.",
        allow_current_device_fallback=False,
        expected_device_key=expected,
    )
    incident_id = center.autopilot_incident.incident_id
    assert center.autopilot_incident.device_key == expected
    assert center.autopilot_incident.mode == "disconnected"

    center.set_devices([other])
    center.set_devices([other])
    app.processEvents()
    assert center.autopilot_incident.incident_id == incident_id
    assert center.autopilot_incident.mode == "disconnected"
    assert "waiting for the phone involved" in center.digest.text()
    assert len(center.autopilot_service.list_recent()) == 1

    center.set_devices([original])
    app.processEvents()
    assert center.autopilot_incident.incident_id == incident_id
    assert center.autopilot_incident.device_key == expected
    assert center.autopilot_incident.mode == "adb"
    assert len(center.autopilot_service.list_recent()) == 1
    assert not center.autopilot_incident.phone_changed
    center.close()


def test_recovery_incident_automatically_scans_local_archives_from_typed_failure(
    tmp_path,
) -> None:
    app = QApplication.instance() or QApplication([])
    center = RepairCenter(
        DiagnosticAnalyzer(),
        RepairAssessmentTemplates(),
        GuardianPreflight(),
        tmp_path,
        ActivityStore(tmp_path),
        offline_service=OfflineKnowledgeService(tmp_path),
    )
    target = device(state=DeviceState.FASTBOOT)

    created = center.open_recovery_incident(
        RecoveryTrigger.FLASH_FAILURE,
        target_device=target,
        message="A reviewed super write did not return a terminal result.",
        failure=KnowledgeFailure(
            phase="source-installation",
            message="Fastboot transport vanished during super write.",
            finding_ids=("source.installation.command_outcome_unknown",),
            partition="super",
            operation="flash super",
        ),
    )
    app.processEvents()

    assert created
    assert center._autopilot_knowledge_report is not None
    assert center._autopilot_knowledge_report.trigger == "source-installation-failure"
    assert center._autopilot_knowledge_report.execution_authority == "none"
    assert center.autopilot_incident is not None
    assert center.autopilot_incident.knowledge_archive_digest
    assert not center.autopilot_incident.phone_changed
    center.close()


def test_recovery_authorization_route_checks_in_place_without_navigation(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    center = RepairCenter(
        DiagnosticAnalyzer(),
        RepairAssessmentTemplates(),
        GuardianPreflight(),
        tmp_path,
        ActivityStore(tmp_path),
    )
    center.set_devices([device(state=DeviceState.UNAUTHORIZED)])
    center.open_recovery_incident(RecoveryTrigger.DEVICE_MODE)
    requested: list[tuple[str, str]] = []
    scans = []
    center.autopilot_route_requested.connect(
        lambda owner, route: requested.append((owner, route))
    )
    center.verification_scan_requested.connect(lambda: scans.append(True))

    assert center.autopilot_route_buttons[0].text() == "Check authorization now"
    center.autopilot_route_buttons[0].click()
    app.processEvents()

    assert requested == []
    assert scans == [True]
    assert "keep this Recovery incident open" in center.digest.text()
    assert center.host_repair_worker is None
    assert center.autopilot_incident is not None
    assert center.autopilot_incident.events[-1].event_type == "route_reviewed"
    assert not center.autopilot_incident.phone_changed
    center.close()


def test_recovery_fastboot_identity_refresh_stays_in_recovery_bay(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    center = RepairCenter(
        DiagnosticAnalyzer(),
        RepairAssessmentTemplates(),
        GuardianPreflight(),
        tmp_path,
        ActivityStore(tmp_path),
    )
    center.set_devices([device(state=DeviceState.FASTBOOT)])
    center.open_recovery_incident(RecoveryTrigger.BOOTLOOP)
    routes = []
    scans = []
    center.autopilot_route_requested.connect(
        lambda owner, route: routes.append((owner, route))
    )
    center.verification_scan_requested.connect(lambda: scans.append(True))

    refresh = next(
        button
        for button in center.autopilot_route_buttons
        if button.text() == "Refresh identity now"
    )
    refresh.click()
    app.processEvents()

    assert routes == []
    assert scans == [True]
    assert center.autopilot_incident is not None
    assert center.autopilot_incident.events[-1].event_type == "route_reviewed"
    assert "keep this Recovery incident open" in center.digest.text()
    assert not center.autopilot_incident.phone_changed
    center.close()


def test_recovery_local_guidance_is_inline_instead_of_a_modal_dead_end(
    tmp_path, monkeypatch
) -> None:
    app = QApplication.instance() or QApplication([])
    center = RepairCenter(
        DiagnosticAnalyzer(),
        RepairAssessmentTemplates(),
        GuardianPreflight(),
        tmp_path,
        ActivityStore(tmp_path),
    )
    center.open_recovery_incident(RecoveryTrigger.MANUAL_DIAGNOSIS)
    modal_calls = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *args, **kwargs: modal_calls.append((args, kwargs)),
    )

    assert center.autopilot_route_buttons[0].text() == "Show guidance"
    center.autopilot_route_buttons[0].click()
    app.processEvents()

    assert modal_calls == []
    assert "This guidance did not start a phone action" in center.digest.text()
    assert center.autopilot_incident is not None
    assert not center.autopilot_incident.phone_changed
    center.close()


def test_recovery_external_owner_route_still_uses_typed_handoff(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    center = RepairCenter(
        DiagnosticAnalyzer(),
        RepairAssessmentTemplates(),
        GuardianPreflight(),
        tmp_path,
        ActivityStore(tmp_path),
        offline_service=OfflineKnowledgeService(tmp_path),
    )
    center.open_recovery_incident(
        RecoveryTrigger.FLASH_FAILURE,
        target_device=device(state=DeviceState.FASTBOOT),
        failure=KnowledgeFailure(
            phase="source-installation",
            message="Fastboot transport vanished during super write.",
            finding_ids=("source.installation.command_outcome_unknown",),
            partition="super",
            operation="flash super",
        ),
    )
    incident = center.autopilot_incident
    assert incident is not None
    route = next(
        route
        for route in incident.routes
        if route.kind is RecoveryRouteKind.ARCHIVES_REVIEW
    )
    center._autopilot_show_all_routes = True
    center._render_autopilot()
    context = center.recovery_route_context(route.route_id, "archives")
    assert context is not None
    assert context[0].incident_id == incident.incident_id
    assert context[1] == route
    assert center.recovery_route_context(route.route_id, "guardian_core") is None
    assert not center.restore_recovery_route("different-incident", route.route_id)
    requested = []
    center.autopilot_route_requested.connect(
        lambda owner, route_id: requested.append((owner, route_id))
    )

    button = next(
        button
        for button in center.autopilot_route_buttons
        if route.title in button.accessibleName()
    )
    assert button.text() == "Continue to route"
    button.click()
    app.processEvents()

    assert requested == [("archives", route.route_id)]
    assert center.autopilot_incident is not None
    assert center.autopilot_incident.events[-1].event_type == "route_reviewed"
    assert not center.autopilot_incident.phone_changed
    assert center.restore_recovery_route(incident.incident_id, route.route_id)
    restored = next(
        item
        for item in center.autopilot_route_buttons
        if item.property("recovery_route_id") == route.route_id
    )
    assert restored is not None
    assert "remains advisory" in center.digest.text()
    center.close()


def test_recovery_autopilot_keeps_every_ranked_route_reviewable(
    tmp_path, monkeypatch
) -> None:
    app = QApplication.instance() or QApplication([])
    center = RepairCenter(
        DiagnosticAnalyzer(),
        RepairAssessmentTemplates(),
        GuardianPreflight(),
        tmp_path,
        ActivityStore(tmp_path),
    )
    center.open_recovery_incident(RecoveryTrigger.MANUAL_DIAGNOSIS)
    incident = center.autopilot_incident
    assert incident is not None
    template = incident.routes[0]
    routes = tuple(
        replace(
            template,
            route_id=f"recovery.presentation-{rank}",
            title=f"Ranked recovery route {rank}",
            rank=rank,
        )
        for rank in range(1, 6)
    )
    center.autopilot_incident = replace(incident, routes=routes)
    center._render_autopilot()
    app.processEvents()

    assert len(center.autopilot_route_buttons) == 4
    show_all = next(
        button
        for button in center.findChildren(QPushButton)
        if button.text() == "Show all 5 ranked routes"
    )
    show_all.click()
    app.processEvents()
    assert len(center.autopilot_route_buttons) == 5
    assert any(
        button.text() == "Show highest-priority routes"
        for button in center.findChildren(QPushButton)
    )

    shown: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda _parent, _title, text: shown.append(text),
    )
    center.autopilot_timeline_button.click()
    assert shown and "CURRENT RANKED ROUTES" in shown[-1]
    assert "Ranked recovery route 5" in shown[-1]
    center.close()


def test_recovery_bay_does_not_restart_healthy_or_unauthorized_adb(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    service, runner = host_repair_service(tmp_path)
    center = RepairCenter(
        DiagnosticAnalyzer(),
        RepairAssessmentTemplates(),
        GuardianPreflight(),
        tmp_path,
        ActivityStore(tmp_path),
        host_repair_service=service,
    )
    usb_index = center.concern_selector.findData(RepairConcern.USB_ADB.value)

    center.set_devices([device(state=DeviceState.DEVICE)])
    center.concern_selector.setCurrentIndex(usb_index)
    app.processEvents()
    assert center.host_repair_plan is None
    assert center.host_repair_button is None
    assert any(
        "NO SAFE AUTOMATIC ACTION NEEDED" in label.text() for label in center.findChildren(QLabel)
    )

    center.set_devices([device(state=DeviceState.UNAUTHORIZED)])
    app.processEvents()
    assert center.host_repair_plan is None
    assert center.host_repair_button is None
    assert any("USER ACTION REQUIRED" in label.text() for label in center.findChildren(QLabel))
    assert runner.calls == []
    center.close()


def test_recovery_bay_automatically_researches_exact_error_without_executing_remote_text(
    tmp_path, monkeypatch
) -> None:
    app = QApplication.instance() or QApplication([])
    online = OnlineRemediationService(tmp_path, (OfficialAdbResearchProvider(),))
    monkeypatch.setattr(
        "romverse.ui.repair_center.start_background",
        lambda worker: worker.execute(),
    )
    center = RepairCenter(
        DiagnosticAnalyzer(),
        RepairAssessmentTemplates(),
        GuardianPreflight(),
        tmp_path,
        ActivityStore(tmp_path),
        online_service=online,
    )
    center.symptom_input.setText("ADB device offline after USB reconnect")
    center.set_devices([device(state=DeviceState.OFFLINE)])
    app.processEvents()

    assert center.intelligence_card.isVisibleTo(center)
    assert not center.intelligence_details.isHidden()
    assert center.intelligence_toggle.isChecked()
    assert "OFFICIAL" in center.intelligence_status.text()
    assert "90%" in center.intelligence_status.text()
    assert "developer.android.com" in center.intelligence_source.text()
    assert "guidance only" in center.intelligence_boundary.text().casefold()
    assert "execution authority: none" in center.intelligence_boundary.text().casefold()
    assert not center.intelligence_action.isHidden()
    assert "USB / ADB" in center.intelligence_action.text()
    center.intelligence_action.click()
    app.processEvents()
    assert "no scan, daemon restart, or phone action started" in center.digest.text()
    assert center.host_repair_worker is None
    assert not list((tmp_path / "diagnostics" / "host-repair-receipts").glob("*"))
    center.close()


def test_recovery_bay_emits_only_a_current_revalidated_typed_solution_handoff(
    tmp_path, monkeypatch
) -> None:
    app = QApplication.instance() or QApplication([])
    online = OnlineRemediationService(tmp_path, (OfficialPlatformToolsProvider(),))
    monkeypatch.setattr(
        "romverse.ui.repair_center.start_background",
        lambda worker: worker.execute(),
    )
    center = RepairCenter(
        DiagnosticAnalyzer(),
        RepairAssessmentTemplates(),
        GuardianPreflight(),
        tmp_path,
        ActivityStore(tmp_path),
        online_service=online,
    )
    center.symptom_input.setText("platform tools command not found")
    center.set_devices([device()])
    app.processEvents()

    requested: list[tuple[str, str, str, str]] = []
    center.solution_action_requested.connect(
        lambda *values: requested.append(tuple(str(value) for value in values))
    )
    assert not center.intelligence_action.isHidden()
    assert center.intelligence_action.text() == "Open Platform Tools verification"
    binding = center._intelligence_action_binding
    assert binding is not None
    assert center.validate_solution_handoff(*binding)

    center.intelligence_action.click()
    app.processEvents()
    assert requested == [binding]
    assert center.host_repair_worker is None

    center._online_current = ErrorFingerprint.create("different current evidence")
    center.intelligence_action.click()
    app.processEvents()
    assert requested == [binding]
    assert center.intelligence_action.isHidden()
    assert "HANDOFF STOPPED" in center.intelligence_status.text()
    center.close()


def test_recovery_bay_synthesizes_and_displays_ranked_solution_evidence(
    tmp_path, monkeypatch
) -> None:
    app = QApplication.instance() or QApplication([])
    online = OnlineRemediationService(tmp_path, (MultiSourceResearchProvider(),))
    monkeypatch.setattr(
        "romverse.ui.repair_center.start_background",
        lambda worker: worker.execute(),
    )
    center = RepairCenter(
        DiagnosticAnalyzer(),
        RepairAssessmentTemplates(),
        GuardianPreflight(),
        tmp_path,
        ActivityStore(tmp_path),
        online_service=online,
    )
    center.symptom_input.setText("system update failed after download")
    center.set_devices([device(manufacturer="Samsung")])
    app.processEvents()

    assert "SMART SOLUTION BRIEF • OFFICIAL GUIDANCE" in center.intelligence_decision.text()
    assert "NEXT SAFE MOVE" in center.intelligence_decision.text()
    ranked_sources = center.intelligence_source.text()
    assert ranked_sources.count("href=") == 3
    assert "LEAD" in ranked_sources
    assert "ALTERNATIVE 1" in ranked_sources
    assert "Samsung official update guidance" in ranked_sources
    assert "Maintainer update diagnosis" in ranked_sources
    assert "Community update report" in ranked_sources
    assert "OFFICIAL GUIDANCE" in ranked_sources
    assert "MAINTAINER GUIDANCE" in ranked_sources
    assert "COMMUNITY REPORT" in ranked_sources
    assert center._report_payload is not None
    research = center._report_payload["online_research"]
    assert isinstance(research, dict)
    assert research["decision_state"] == "official-guidance"
    assert research["candidate_count"] == 3
    assert research["lead_signal"] == "official-guidance"
    assert research["execution_authority"] == "guidance-only"
    assert not research["phone_action_allowed"]
    assert center.host_repair_worker is None
    center.close()


def test_recovery_bay_smart_solution_copy_remains_visible_at_desktop_sizes(
    tmp_path, monkeypatch
) -> None:
    app = QApplication.instance() or QApplication([])
    online = OnlineRemediationService(tmp_path, (MultiSourceResearchProvider(),))
    monkeypatch.setattr(
        "romverse.ui.repair_center.start_background",
        lambda worker: worker.execute(),
    )
    center = RepairCenter(
        DiagnosticAnalyzer(),
        RepairAssessmentTemplates(),
        GuardianPreflight(),
        tmp_path,
        ActivityStore(tmp_path),
        online_service=online,
    )
    center.resize(1_280, 720)
    center.show()
    center.symptom_input.setText("system update failed after download")
    center.set_devices([device(manufacturer="Samsung")])

    for _ in range(4):
        app.processEvents()

    decision = center.intelligence_decision
    text_height = (
        decision.fontMetrics()
        .boundingRect(
            decision.rect(),
            int(Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignLeft),
            decision.text(),
        )
        .height()
    )
    assert decision.height() >= text_height
    assert center.intelligence_detail.geometry().top() > decision.geometry().bottom()

    center.resize(960, 720)
    for _ in range(4):
        app.processEvents()
    text_height = (
        decision.fontMetrics()
        .boundingRect(
            decision.rect(),
            int(Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignLeft),
            decision.text(),
        )
        .height()
    )
    assert decision.height() >= text_height
    assert center.intelligence_detail.geometry().top() > decision.geometry().bottom()
    center.close()


def test_recovery_bay_successful_typed_host_repair_promotes_only_matching_official_fix(
    tmp_path, monkeypatch
) -> None:
    app = QApplication.instance() or QApplication([])
    host_service, runner = host_repair_service(tmp_path)
    online = OnlineRemediationService(tmp_path, (OfficialAdbResearchProvider(),))
    monkeypatch.setattr(
        "romverse.ui.repair_center.start_background",
        lambda worker: worker.execute(),
    )
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    center = RepairCenter(
        DiagnosticAnalyzer(),
        RepairAssessmentTemplates(),
        GuardianPreflight(),
        tmp_path,
        ActivityStore(tmp_path),
        host_repair_service=host_service,
        online_service=online,
    )
    center.symptom_input.setText("ADB device offline after USB reconnect")
    center.set_devices([device(state=DeviceState.OFFLINE)])
    center.concern_selector.setCurrentIndex(
        center.concern_selector.findData(RepairConcern.USB_ADB.value)
    )
    app.processEvents()
    assert center.host_repair_button is not None
    fingerprint = center._online_current
    assert fingerprint is not None

    center.host_repair_button.click()
    app.processEvents()

    refreshed = online.lookup(fingerprint)
    candidate = next(
        item for item in refreshed.candidates if item.local_action_id == "refresh-adb-evidence"
    )
    assert candidate.confirmed_working
    assert "LOCALLY VERIFIED WORKING" in center.intelligence_status.text()
    assert all("-s" not in call for call in runner.calls)
    assert requested_phone_commands(runner.calls) == []
    center.close()


def test_recovery_bay_discards_in_flight_online_result_when_setting_is_disabled(
    tmp_path, monkeypatch
) -> None:
    app = QApplication.instance() or QApplication([])
    online = OnlineRemediationService(tmp_path, (OfficialAdbResearchProvider(),))
    workers = []
    monkeypatch.setattr(
        "romverse.ui.repair_center.start_background",
        lambda worker: workers.append(worker),
    )
    center = RepairCenter(
        DiagnosticAnalyzer(),
        RepairAssessmentTemplates(),
        GuardianPreflight(),
        tmp_path,
        ActivityStore(tmp_path),
        online_service=online,
    )
    center.symptom_input.setText("ADB device offline")
    center.set_devices([device(state=DeviceState.OFFLINE)])
    assert len(workers) == 1

    center.set_online_service(None)
    workers[0].execute()
    app.processEvents()

    assert center.online_service is None
    assert center.intelligence_card.isHidden()
    assert "OFFICIAL" not in center.intelligence_status.text()
    center.close()


def requested_phone_commands(calls: list[tuple[str, ...]]) -> list[tuple[str, ...]]:
    return [call for call in calls if "-s" in call or "fastboot" in call]
