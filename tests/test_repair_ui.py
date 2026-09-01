from __future__ import annotations

import os
from importlib.resources import files

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel, QMessageBox, QPushButton

from romverse.core.activity import ActivityStore
from romverse.device.models import DeviceState
from romverse.device_packs.registry import DevicePackRegistry
from romverse.diagnostics.analyzer import DiagnosticAnalyzer
from romverse.guardian.approval import ApprovalStore
from romverse.guardian.gateway import ExecutionGateway
from romverse.guardian.planning import GuardianPreflight
from romverse.guardian.policy import GuardianPolicy
from romverse.infrastructure.process import CommandResult
from romverse.intelligence.online_remediation import (
    OnlineFixCandidate,
    OnlineRemediationService,
    SourceAuthority,
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


def test_guided_repair_ui_saves_checkpoints_then_requires_fresh_scan(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    center = RepairCenter(
        DiagnosticAnalyzer(),
        RepairAssessmentTemplates(),
        GuardianPreflight(),
        tmp_path,
        ActivityStore(tmp_path),
    )
    center.set_devices([device(battery_percent=8)])
    center._start_session()
    app.processEvents()
    assert center.active_session is not None
    assert center.active_session.status == "active"
    assert center.active_session.archive_article_keys == ("device-battery-low",)

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
    assert center.host_repair_worker is None
    assert not list((tmp_path / "diagnostics" / "host-repair-receipts").glob("*"))
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
