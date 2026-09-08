from __future__ import annotations

import hashlib
import os
import sys
from dataclasses import replace
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QFrame, QLabel, QPushButton

from romverse.core.privacy import WorkspacePrivacy
from romverse.core.settings import AppSettings, DesktopTheme, ExperienceMode
from romverse.device.catalog import (
    GOOGLE_PLAY_CATALOG_URL,
    DeviceCatalogError,
    DeviceCatalogStatus,
    DeviceCatalogUpdate,
    GooglePlayDeviceCatalog,
)
from romverse.device.identity import IdentityAuthority
from romverse.device.models import AndroidDevice, DeviceState, StorageInfo
from romverse.device_packs.registry import DevicePackRegistry
from romverse.guardian.audit import GuardianAuditStore
from romverse.guardian.gateway import ExecutionGateway
from romverse.guardian.manifest_review import GuardianManifestReviewService
from romverse.guardian.policy import GuardianPolicy
from romverse.infrastructure.process import CommandResult
from romverse.infrastructure.tools import ToolStatus
from romverse.intelligence.online_remediation import ErrorFingerprint, OnlineRemediationService
from romverse.intelligence.synapse import (
    SynapseContribution,
    SynapseKnowledgeState,
    SynapseScope,
    SynapseStore,
)
from romverse.knowledge.models import KnowledgeQuery
from romverse.nexus.events import MissionConfidence, MissionState
from romverse.nexus.planning import NexusObjective, NexusPlanner
from romverse.repair.autopilot import RecoveryRouteKind, RecoveryTrigger
from romverse.repair.templates import RepairConcern
from romverse.rom.boot_observation import (
    BootFailureKind,
    BootObservationReceipt,
    BootObservationStatus,
    BootSample,
)
from romverse.rom.first_light import (
    FirstLightOverall,
    FirstLightReport,
)
from romverse.rom.inspection import RomInspectionService
from romverse.rom.projects import RomProjectStore
from romverse.rom.source_intelligence import FirmwareSourceIntelligenceService
from romverse.ui.main_window import (
    MainWindow,
    _device_scan_failure_copy,
    _device_scan_failure_is_transient,
    _sidebar_device_art_kind,
    _sidebar_nav_tooltip,
)
from romverse.ui.theme import STYLESHEET
from tests.test_apk_center_ui import _device as _apk_device
from tests.test_apk_center_ui import _ready_plan as _apk_ready_plan
from tests.test_device_catalog import _payload, _sync
from tests.test_device_dna import _device, _project, _source
from tests.test_guardian_manifest_review import _prepared as _prepared_guardian_manifest
from tests.test_recovery_autopilot import _device as _recovery_device
from tests.test_recovery_autopilot import _registry as _recovery_registry
from tests.test_recovery_autopilot import _verified_boot as _recovery_verified_boot
from tests.test_source_intelligence import SourceRunner


def test_bootloop_evidence_automatically_opens_recovery_autopilot(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    store, registry, project, _report = _project(tmp_path)
    phone = _device(
        state=DeviceState.FASTBOOT,
        boot_completed=False,
        uptime_seconds=10,
    )
    window = MainWindow(None, logo, store.workspace, app_icon_path=logo, pack_registry=registry)
    try:
        window.rom_studio.refresh(project.project_id)
        window.rom_studio.devices = [phone]
        window.repair_center.set_devices([phone])
        sample = BootSample(
            datetime.now(UTC).isoformat(),
            WorkspacePrivacy(store.workspace).pseudonym(phone.serial),
            DeviceState.FASTBOOT.value,
            False,
            10,
            "_a",
            phone.build_id,
            phone.build_fingerprint,
            phone.battery_percent,
            (),
        )
        receipt = BootObservationReceipt(
            3,
            project.project_id,
            project.device_pack_id,
            registry.packs[0].build_contract.contract_id,
            project.original.sha256,
            (sample,),
            BootObservationStatus.ATTENTION,
            False,
            True,
            True,
            "b" * 64,
            False,
            "Repeated restart evidence was measured after the verified flash.",
            False,
            BootFailureKind.REBOOT_LOOP,
            ("boot loop after flash",),
            "c" * 64,
        )

        window._handle_boot_observation(receipt, None)
        app.processEvents()

        assert window.stack.currentWidget() is window.repair_center
        assert window.repair_center.autopilot_incident is not None
        assert window.repair_center.autopilot_incident.trigger is RecoveryTrigger.BOOTLOOP
        assert not window.repair_center.autopilot_incident.repaired
        assert window.repair_center.autopilot_card.isVisibleTo(window.repair_center)
        assert window.rom_studio.worker is None
        assert window.repair_center.host_repair_worker is None

    finally:
        window.companion_center.transport.close()
        window.close()


def test_recovery_boot_check_stays_in_journey_and_closes_only_on_fresh_proof(
    tmp_path: Path,
) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    phone = _recovery_device(DeviceState.DEVICE, boot_completed=False, uptime_seconds=20)
    window = MainWindow(
        None,
        logo,
        tmp_path,
        app_icon_path=logo,
        pack_registry=_recovery_registry(),
    )
    scans = []
    window.repair_center.verification_scan_requested.connect(lambda: scans.append(True))
    try:
        window.repair_center.set_devices([phone])
        assert window.repair_center.open_recovery_incident(
            RecoveryTrigger.BOOTLOOP,
            project_id="project-one",
            target_device=phone,
        )
        assert window._navigate_route("recovery_bay")
        incident = window.repair_center.autopilot_incident
        assert incident is not None
        observe = next(
            button
            for button in window.repair_center.autopilot_route_buttons
            if button.text() == "Check boot progress now"
        )

        observe.click()
        app.processEvents()

        assert scans == [True]
        assert window.stack.currentWidget() is window.repair_center
        assert window.repair_center.autopilot_incident is not None
        assert window.repair_center.autopilot_incident.incident_id == incident.incident_id
        recovered = replace(phone, boot_completed=True, uptime_seconds=600)
        window.repair_center.set_devices([recovered])
        window._handle_boot_observation(
            _recovery_verified_boot(tmp_path, recovered),
            None,
        )
        app.processEvents()

        closed = window.repair_center.autopilot_incident
        assert closed is not None
        assert closed.incident_id == incident.incident_id
        assert closed.repaired
        assert closed.verified_reboot
        assert closed.routes == ()
        assert not closed.phone_changed
        assert len(window.repair_center.autopilot_service.list_recent()) == 1
        assert window.stack.currentWidget() is window.repair_center
    finally:
        window.companion_center.transport.close()
        window.close()


def test_recovery_archives_handoff_opens_exact_records_and_returns_to_same_incident(
    tmp_path: Path,
) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    phone = _recovery_device(DeviceState.RECOVERY, boot_completed=False)
    window = MainWindow(
        None,
        logo,
        tmp_path,
        app_icon_path=logo,
        pack_registry=_recovery_registry(),
    )
    report = window.offline_knowledge_service.lookup(
        KnowledgeQuery(
            error_codes=("HASH_MISMATCH(3)",),
            symptoms=("verified boot failure after update",),
        )
    )
    try:
        window.repair_center.set_devices([phone])
        assert window.repair_center.open_recovery_incident(
            RecoveryTrigger.BOOTLOOP,
            project_id="project-one",
            target_device=phone,
            knowledge_report=report,
        )
        assert window._navigate_route("recovery_bay")
        incident = window.repair_center.autopilot_incident
        assert incident is not None
        route = next(
            item for item in incident.routes if item.kind is RecoveryRouteKind.ARCHIVES_REVIEW
        )
        window.repair_center._autopilot_show_all_routes = True
        window.repair_center._render_autopilot()
        archives = next(
            button
            for button in window.repair_center.autopilot_route_buttons
            if button.property("recovery_route_id") == route.route_id
        )

        archives.click()
        app.processEvents()

        assert window.stack.currentWidget() is window.knowledge_center
        assert window.knowledge_center.recovery_review_identity == (
            incident.incident_id,
            route.route_id,
        )
        assert window.knowledge_center.source_return.text() == "Return to Recovery incident"
        opened_ids = tuple(
            str(window.knowledge_center.list.item(row).data(Qt.ItemDataRole.UserRole)).removeprefix(
                "offline:"
            )
            for row in range(window.knowledge_center.list.count())
        )
        assert opened_ids == route.knowledge_record_ids

        window.knowledge_center.source_return.click()
        app.processEvents()

        assert window.stack.currentWidget() is window.repair_center
        restored = window.repair_center.autopilot_incident
        assert restored is not None
        assert restored.incident_id == incident.incident_id
        assert any(item.route_id == route.route_id for item in restored.routes)
        assert not restored.phone_changed
        assert window.knowledge_center.recovery_review_identity is None
        assert window.rom_studio.worker is None
        assert window.guardian_center.worker is None

        window.repair_center._autopilot_show_all_routes = True
        window.repair_center._render_autopilot()
        archives = next(
            button
            for button in window.repair_center.autopilot_route_buttons
            if button.property("recovery_route_id") == route.route_id
        )
        archives.click()
        app.processEvents()
        assert window.stack.currentWidget() is window.knowledge_center
        window.repair_center.autopilot_incident = replace(
            window.repair_center.autopilot_incident,
            repaired=True,
            routes=(),
        )

        window.knowledge_center.source_return.click()
        app.processEvents()

        assert window.stack.currentWidget() is window.knowledge_center
        assert window.knowledge_center.recovery_review_identity is None
        assert "expired safely" in window.knowledge_center.search_status.text()
        assert "did not substitute" in window.knowledge_center.detail.toPlainText()
        assert window.knowledge_center.list.count() == 0
    finally:
        window.companion_center.transport.close()
        window.close()


def test_recovery_guardian_handoff_returns_to_same_incident_and_route(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    phone = _recovery_device(DeviceState.FASTBOOT, boot_completed=False)
    window = MainWindow(
        None,
        logo,
        tmp_path,
        app_icon_path=logo,
        pack_registry=_recovery_registry(),
    )
    try:
        window.repair_center.set_devices([phone])
        assert window.repair_center.open_recovery_incident(
            RecoveryTrigger.BOOTLOOP,
            project_id="recovery-project",
            target_device=phone,
        )
        assert window._navigate_route("recovery_bay")
        incident = window.repair_center.autopilot_incident
        assert incident is not None
        route = next(item for item in incident.routes if item.owner_route == "guardian_core")
        window.repair_center._autopilot_show_all_routes = True
        window.repair_center._render_autopilot()
        window.guardian_center.request_refresh = lambda: None
        route_button = next(
            button
            for button in window.repair_center.autopilot_route_buttons
            if button.property("recovery_route_id") == route.route_id
        )

        route_button.click()
        app.processEvents()

        assert window.stack.currentWidget() is window.guardian_center
        assert window.guardian_center.recovery_review_identity == (
            incident.incident_id,
            route.route_id,
        )
        assert not window.guardian_center.recovery_review.isHidden()
        guardian_detail = window.guardian_center.recovery_technical_detail.text()
        assert "Approval: none" in guardian_detail
        assert "Execution: none" in guardian_detail
        assert "Phone changed: no" in guardian_detail

        window.guardian_center.recovery_return_button.click()
        app.processEvents()

        assert window.stack.currentWidget() is window.repair_center
        assert window.repair_center.autopilot_incident is not None
        assert window.repair_center.autopilot_incident.incident_id == incident.incident_id
        assert not window.repair_center.autopilot_incident.phone_changed
        assert any(
            button.property("recovery_route_id") == route.route_id
            for button in window.repair_center.autopilot_route_buttons
        )
        assert "remains advisory" in window.repair_center.digest.text()
    finally:
        window.companion_center.transport.close()
        window.close()


def test_recovery_time_machine_handoff_returns_to_same_incident_and_route(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    source = tmp_path / "exact-stock.zip"
    source.write_bytes(b"navigation exact stock fixture")
    workspace = tmp_path / "workspace"
    store = RomProjectStore(workspace)
    project = store.create("Recovery evidence project", "test.recovery")
    project = store.import_original(project.project_id, source)
    registry = _recovery_registry()
    pack = registry.packs[0]
    assert pack.build_contract is not None
    write = pack.build_contract.partition_write_contract
    assert write is not None and write.transition_recovery_contract is not None
    transition = write.transition_recovery_contract
    exact_source = replace(
        pack.build_contract.source,
        archive_sha256=project.original.sha256,
    )
    exact_recovery = replace(
        transition.recovery,
        stock_package_sha256=project.original.sha256,
    )
    registry = DevicePackRegistry(
        (
            replace(
                pack,
                build_contract=replace(
                    pack.build_contract,
                    source=exact_source,
                    partition_write_contract=replace(
                        write,
                        transition_recovery_contract=replace(
                            transition,
                            recovery=exact_recovery,
                        ),
                    ),
                ),
            ),
        )
    )
    phone = _recovery_device(DeviceState.FASTBOOT, boot_completed=False)
    window = MainWindow(
        None,
        logo,
        workspace,
        app_icon_path=logo,
        pack_registry=registry,
    )
    try:
        window.repair_center.set_devices([phone])
        assert window.repair_center.open_recovery_incident(
            RecoveryTrigger.BOOTLOOP,
            project_id=project.project_id,
            target_device=phone,
        )
        assert window._navigate_route("recovery_bay")
        incident = window.repair_center.autopilot_incident
        assert incident is not None
        route = next(
            item for item in incident.routes if item.kind is RecoveryRouteKind.EXACT_STOCK_RESTORE
        )
        assert route.owner_route == "time_machine"
        window.repair_center._autopilot_show_all_routes = True
        window.repair_center._render_autopilot()
        route_button = next(
            button
            for button in window.repair_center.autopilot_route_buttons
            if button.property("recovery_route_id") == route.route_id
        )

        route_button.click()
        app.processEvents()

        assert window.stack.currentWidget() is window.backup_center
        assert window.backup_center.recovery_review_identity == (
            incident.incident_id,
            route.route_id,
        )
        assert window.backup_center.project_selector.currentData() == project.project_id
        assert not window.backup_center.project_selector.isEnabled()
        assert window.backup_center.evidence_worker is None
        assert window.backup_center.worker is None

        window.backup_center.recovery_return_button.click()
        app.processEvents()

        assert window.stack.currentWidget() is window.repair_center
        assert window.repair_center.autopilot_incident is not None
        assert window.repair_center.autopilot_incident.incident_id == incident.incident_id
        assert not window.repair_center.autopilot_incident.phone_changed
        assert window.backup_center.recovery_review_identity is None
        assert window.backup_center.project_selector.isEnabled()
        assert any(
            button.property("recovery_route_id") == route.route_id
            for button in window.repair_center.autopilot_route_buttons
        )
        assert "remains advisory" in window.repair_center.digest.text()

        window.backup_center.recovery_evidence.register(
            project.project_id,
            "external_backup",
            source,
        )
        return_route = next(
            item
            for item in window.repair_center.autopilot_incident.routes
            if item.route_id == route.route_id
        )
        assert return_route.owner_route == "time_machine"
        return_button = next(
            button
            for button in window.repair_center.autopilot_route_buttons
            if button.property("recovery_route_id") == route.route_id
        )
        return_button.click()
        app.processEvents()
        assert window.stack.currentWidget() is window.backup_center
        queued = []
        monkeypatch.setattr("romverse.ui.backup_center.start_background", queued.append)

        window.backup_center._start_recovery_evidence(
            "register",
            project.project_id,
            "stock_recovery",
            source,
        )
        assert len(queued) == 1
        queued.pop().run()
        app.processEvents()

        assert window.stack.currentWidget() is window.repair_center
        assert window.repair_center.autopilot_incident is not None
        assert window.repair_center.autopilot_incident.incident_id == incident.incident_id
        reranked = next(
            item
            for item in window.repair_center.autopilot_incident.routes
            if item.route_id == route.route_id
        )
        assert reranked.owner_route == "guardian_core"
        assert reranked.execution_authority == "none"
        assert window.backup_center.recovery_review_identity is None
        assert window.backup_center.evidence_worker is None
        assert not window.repair_center.autopilot_incident.phone_changed

        window.repair_center._autopilot_show_all_routes = True
        window.repair_center._render_autopilot()
        prepared_button = next(
            button
            for button in window.repair_center.autopilot_route_buttons
            if button.property("recovery_route_id") == reranked.route_id
        )
        audit = GuardianAuditStore(workspace)
        window._runtime_gateway = ExecutionGateway(GuardianPolicy(workspace), SourceRunner(), audit)
        window._device_adb_executable = tmp_path / "inert-adb-fixture"
        window._device_fastboot_executable = tmp_path / "inert-fastboot-fixture"
        window.guardian_center.request_refresh = lambda: None
        recovery_checks = []
        monkeypatch.setattr("romverse.ui.guardian_center.start_background", recovery_checks.append)
        prepared_button.click()
        app.processEvents()

        assert window.stack.currentWidget() is window.guardian_center
        assert window.guardian_center.recovery_review_identity is not None
        assert window.guardian_center.recovery_preparation_digest
        assert window.guardian_center.recovery_review_badge.text() == ("PREPARED • ZERO AUTHORITY")
        assert (
            window.guardian_center.recovery_review_eyebrow.text()
            == "RECOVERY AUTOPILOT  •  EXACT PREPARATION"
        )
        prepared_detail = window.guardian_center.recovery_technical_detail.text()
        assert project.original.sha256 in prepared_detail
        assert "restore stock package" in prepared_detail
        assert "Guardian live-target validation: required" in prepared_detail
        assert "User confirmation: required" in prepared_detail
        assert "Execution: none" in prepared_detail
        assert "Phone changed: no" in prepared_detail
        assert window.guardian_center.recovery_target_button.isVisibleTo(window.guardian_center)
        assert not window.guardian_center.recovery_target_button.isEnabled()
        assert window.guardian_center.hero.isHidden()
        assert window.guardian_center.runtime_package_card.isHidden()
        assert window.guardian_center.body.isHidden()
        assert "CHECKING YOUR PHONE" in (window.guardian_center.recovery_target_status.text())
        assert len(recovery_checks) == 1
        recovery_checks.pop().run()
        app.processEvents()
        assert "PHONE CHECK NEEDS ATTENTION" in (
            window.guardian_center.recovery_target_status.text()
        )

        window.guardian_center.recovery_return_button.click()
        app.processEvents()
        assert window.stack.currentWidget() is window.repair_center
        assert window.repair_center.autopilot_incident is not None
        assert window.repair_center.autopilot_incident.incident_id == incident.incident_id
        assert not window.repair_center.autopilot_incident.phone_changed

        window.repair_center._autopilot_show_all_routes = True
        window.repair_center._render_autopilot()
        next(
            button
            for button in window.repair_center.autopilot_route_buttons
            if button.property("recovery_route_id") == reranked.route_id
        ).click()
        app.processEvents()
        assert window.stack.currentWidget() is window.guardian_center
        assert window.guardian_center.recovery_preparation_digest
        sealed_preparation_digest = window.guardian_center.recovery_preparation_digest
        assert len(recovery_checks) == 1
        recovery_checks.pop().run()
        app.processEvents()

        substitute = replace(phone, serial="same-model-substitute")
        window.repair_center.set_devices([substitute])
        window._revalidate_guardian_review_contexts()
        assert window.guardian_center.recovery_review_identity == (
            incident.incident_id,
            reranked.route_id,
        )
        assert window.guardian_center.recovery_preparation_digest == sealed_preparation_digest
        assert window.guardian_center.recovery_review_badge.text() == "PREPARED • ZERO AUTHORITY"
        assert "WAITING FOR THE PHONE IN THIS RECOVERY INCIDENT" in (
            window.guardian_center.recovery_target_status.text()
        )
        assert not window.guardian_center.recovery_target_button.isEnabled()

        window.repair_center.set_devices([phone, substitute])
        window._revalidate_guardian_review_contexts()
        app.processEvents()
        assert window.guardian_center.recovery_preparation_digest == sealed_preparation_digest
        assert "WAITING FOR THE PHONE IN THIS RECOVERY INCIDENT" in (
            window.guardian_center.recovery_target_status.text()
        )

        window.repair_center.set_devices([phone])
        window._revalidate_guardian_review_contexts()
        app.processEvents()
        assert len(recovery_checks) == 1
        assert "CHECKING YOUR PHONE" in window.guardian_center.recovery_target_status.text()
    finally:
        window.companion_center.transport.close()
        window.close()


def test_first_light_failure_automatically_opens_recovery_autopilot(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    store, registry, project, _report = _project(tmp_path)
    phone = _device(state=DeviceState.DEVICE, boot_completed=True, uptime_seconds=900)
    other_phone = replace(phone, serial="SECOND-PHONE", model="Different phone")
    window = MainWindow(None, logo, store.workspace, app_icon_path=logo, pack_registry=registry)
    try:
        window.rom_studio.refresh(project.project_id)
        # Deliberately make another phone the current Recovery Bay selection. The
        # historical report must still resolve only its own exact device key.
        window.rom_studio.devices = [other_phone, phone]
        window.repair_center.set_devices([other_phone, phone])
        report = FirstLightReport(
            schema_version=1,
            report_id="a" * 32,
            project_id=project.project_id,
            created_at=datetime.now(UTC).isoformat(),
            updated_at=datetime.now(UTC).isoformat(),
            device_key=WorkspacePrivacy(store.workspace).pseudonym(phone.serial),
            pack_id=project.device_pack_id,
            source_sha256=project.original.sha256,
            guardian_execution_receipt_digest="c" * 64,
            boot_observation_digest="d" * 64,
            expected_build_id=phone.build_id,
            observed_build_id=phone.build_id,
            observed_build_fingerprint=phone.build_fingerprint,
            observed_android_version=phone.android_version,
            observed_slot=phone.slot_suffix,
            baseline_scan_id="",
            baseline_changes=(),
            subsystems=(),
            overall=FirstLightOverall.FAILED,
            knowledge_queries=("Android camera failed after ROM flash",),
            public_release_ready=False,
            exportable=True,
            phone_changed=False,
            report_digest="e" * 64,
        )

        window.rom_studio.first_light_updated.emit(report, None)
        app.processEvents()

        assert window.stack.currentWidget() is window.repair_center
        assert window.repair_center.autopilot_incident is not None
        assert window.repair_center.autopilot_incident.trigger is RecoveryTrigger.MANUAL_DIAGNOSIS
        assert window.repair_center.autopilot_incident.device_key == report.device_key
        assert window.repair_center.autopilot_incident.device_name == phone.display_name
        assert "camera failed" in window.repair_center.autopilot_incident.diagnosis.casefold()
        assert window.rom_studio.worker is None
        assert window.repair_center.host_repair_worker is None
    finally:
        window.companion_center.transport.close()
        window.close()


def test_first_light_failure_keeps_sealed_identity_but_stays_targetless_when_phone_absent(
    tmp_path: Path,
) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    store, registry, project, _report = _project(tmp_path)
    report_phone = _device(state=DeviceState.DEVICE, boot_completed=True, uptime_seconds=900)
    selected_phone = replace(report_phone, serial="NEW-SELECTION", model="Unrelated phone")
    window = MainWindow(None, logo, store.workspace, app_icon_path=logo, pack_registry=registry)
    try:
        window.rom_studio.refresh(project.project_id)
        window.rom_studio.devices = [selected_phone]
        window.repair_center.set_devices([selected_phone])
        report = FirstLightReport(
            schema_version=1,
            report_id="f" * 32,
            project_id=project.project_id,
            created_at=datetime.now(UTC).isoformat(),
            updated_at=datetime.now(UTC).isoformat(),
            device_key=WorkspacePrivacy(store.workspace).pseudonym(report_phone.serial),
            pack_id=project.device_pack_id,
            source_sha256=project.original.sha256,
            guardian_execution_receipt_digest="c" * 64,
            boot_observation_digest="d" * 64,
            expected_build_id=report_phone.build_id,
            observed_build_id=report_phone.build_id,
            observed_build_fingerprint=report_phone.build_fingerprint,
            observed_android_version=report_phone.android_version,
            observed_slot=report_phone.slot_suffix,
            baseline_scan_id="",
            baseline_changes=(),
            subsystems=(),
            overall=FirstLightOverall.FAILED,
            knowledge_queries=("Android camera failed after ROM flash",),
            public_release_ready=False,
            exportable=True,
            phone_changed=False,
            report_digest="e" * 64,
        )

        window._handle_first_light(report, None)
        app.processEvents()

        assert window.repair_center.autopilot_incident is not None
        assert window.repair_center.autopilot_incident.device_key == report.device_key
        assert window.repair_center.autopilot_incident.mode == "disconnected"
        assert window.repair_center.autopilot_incident.device_key != WorkspacePrivacy(
            store.workspace
        ).pseudonym(selected_phone.serial)
    finally:
        window.companion_center.transport.close()
        window.close()


def test_every_desktop_navigation_label_opens_and_highlights_its_own_page(
    tmp_path: Path,
) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(None, logo, tmp_path, app_icon_path=logo)
    try:
        labels = [button.text().replace("&&", "&") for button in window.nav_buttons]
        assert labels == [
            "Command Deck",
            "ROM Studio",
            "Quantum Optimizer",
            "Device Atlas",
            "Recovery Bay",
            "Guardian Core",
            "App Launchpad",
            "Time Machine",
            "Health Timeline",
            "Activity Center",
            "ROMVERSE Archives",
            "Command Console",
            "Live Console",
            "ROMVERSE Nexus",
            "Forge Arsenal",
            "ROMVERSE Link",
            "ROMVERSE Members",
            "ROMVERSE Galaxy",
            "About ROMVERSE",
        ]
        assert [heading.text() for heading in window.nav_section_labels] == [
            "HOME",
            "ROM WORKSHOP",
            "DEVICE",
            "GUARDIAN & RECOVERY",
            "ACTIVITY & KNOWLEDGE",
            "LIVE OPERATIONS",
            "CONNECTED ROMVERSE",
            "SYSTEM",
        ]
        routes = [int(button.property("page_index")) for button in window.nav_buttons]
        assert len(routes) == len(set(routes))
        assert window.page_routes == {
            "command_deck": window.stack.indexOf(window.device_center),
            "quantum_optimizer": window.stack.indexOf(window.diagnostics_center),
            "health_timeline": window.stack.indexOf(window.history_center),
            "activity_center": window.stack.indexOf(window.activity_center),
            "guardian_core": window.stack.indexOf(window.guardian_center),
            "recovery_bay": window.stack.indexOf(window.repair_center),
            "device_atlas": window.stack.indexOf(window.device_packs_center),
            "rom_studio": window.stack.indexOf(window.rom_studio),
            "app_launchpad": window.stack.indexOf(window.apk_installer),
            "time_machine": window.stack.indexOf(window.backup_center),
            "archives": window.stack.indexOf(window.knowledge_center),
            "command_console": window.stack.indexOf(window.terminal_center),
            "live_console": window.stack.indexOf(window.live_console),
            "nexus": window.stack.indexOf(window.nexus_center),
            "forge_arsenal": window.stack.indexOf(window.toolchain_center),
            "companion_link": window.stack.indexOf(window.companion_center),
            "members": window.stack.indexOf(window.members_center),
            "galaxy": window.stack.indexOf(window.galaxy_center),
            "about": window.stack.indexOf(window.about_page),
        }

        by_label = {button.text().replace("&&", "&"): button for button in window.nav_buttons}
        assert window.experience_badge.text() == "GUIDED  •  ARCANA"
        assert by_label["Command Console"].isHidden()
        assert by_label["ROMVERSE Nexus"].isHidden()
        assert by_label["Forge Arsenal"].isHidden()
        assert not by_label["Live Console"].isHidden()
        assert not by_label["Guardian Core"].isHidden()

        active_route = window.stack.currentIndex()
        window._apply_experience_mode(ExperienceMode.EXPERT)
        assert window.stack.currentIndex() == active_route
        assert window.experience_badge.text() == "EXPERT  •  ARCHITECT"
        assert not by_label["Command Console"].isHidden()
        assert not by_label["ROMVERSE Nexus"].isHidden()
        assert not by_label["Forge Arsenal"].isHidden()

        for button, route in zip(window.nav_buttons, routes, strict=True):
            window._navigate(route)
            app.processEvents()
            active = [item for item in window.nav_buttons if item.property("active")]
            assert window.stack.currentIndex() == route
            assert active == [button]
            assert button.toolTip()
        active_route = window.stack.currentIndex()
        assert not window._navigate_route("missing internal route")
        assert window.stack.currentIndex() == active_route
        assert window.notification_center.last_notification is not None
        assert window.notification_center.last_notification.key.startswith("navigation.missing.")

        window._navigate_route("about")
        window.about_page.family_buttons["guardian_core"].click()
        app.processEvents()
        assert window.stack.currentWidget() is window.guardian_center
        assert by_label["Guardian Core"].property("active") is True
        assert window.guardian_center.worker is None
    finally:
        window.companion_center.transport.close()
        window.close()


def test_new_archives_owner_routes_open_and_return_to_exact_desktop_pages(
    tmp_path: Path,
) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(
        None,
        logo,
        tmp_path,
        app_icon_path=logo,
        app_settings=AppSettings(online_intelligence_enabled=False),
    )
    owner_guides = (
        (
            "command_console",
            window.terminal_center,
            window.terminal_center.guide_button,
            "command-console-no-trusted-result",
        ),
        (
            "members",
            window.members_center,
            window.members_center.guide_button,
            "members-service-unavailable-or-unconfigured",
        ),
        (
            "galaxy",
            window.galaxy_center,
            window.galaxy_center.guide_button,
            "galaxy-local-publishing-boundary",
        ),
    )
    try:
        window.resize(1_200, 760)
        window.show()
        app.processEvents()
        for route, owner, guide_button, article_key in owner_guides:
            assert window._navigate_route(route)
            app.processEvents()
            assert window.workspace_route_title.width() >= (
                window.workspace_route_title.fontMetrics().horizontalAdvance(
                    window.workspace_route_title.text()
                )
            )
            guide_button.click()
            app.processEvents()

            assert window.stack.currentWidget() is window.knowledge_center
            assert (
                window.knowledge_center.list.currentItem().data(Qt.ItemDataRole.UserRole)
                == article_key
            )
            assert window.knowledge_center.source_context.property("source_route") == route
            assert window.knowledge_center.open_route.property("route") == route
            window.knowledge_center.source_return.click()
            app.processEvents()
            assert window.stack.currentWidget() is owner

        for route, owner, article_key in (
            (
                "health_timeline",
                window.history_center,
                "health-timeline-comparison-unavailable",
            ),
            ("nexus", window.nexus_center, "nexus-current-evidence-route-unavailable"),
        ):
            assert window._navigate_route("archives")
            assert window.knowledge_center.open_article(article_key)
            assert window.knowledge_center.open_route.property("route") == route
            window.knowledge_center.open_route.click()
            app.processEvents()
            assert window.stack.currentWidget() is owner

        assert window.terminal_center._worker is None
        assert not window.members_center._busy
        assert window.guardian_center.worker is None
        assert window.rom_studio.worker is None
    finally:
        window.companion_center.transport.close()
        window.close()


def test_about_recalculates_real_workspace_evidence_and_returns_from_its_exact_guide(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(GooglePlayDeviceCatalog, "MINIMUM_ENTRIES", 1)
    _sync(
        GooglePlayDeviceCatalog(tmp_path),
        _payload(("Example", "Example Nebula", "nebula", "EX-100")),
    )
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    tools = (
        ToolStatus("Python", True, "/verified/python", "3.14", "Ready"),
        ToolStatus("ADB", False, detail="Not ready"),
    )
    window = MainWindow(
        None,
        logo,
        tmp_path,
        pack_registry=registry,
        tool_statuses=tools,
        app_icon_path=logo,
        app_settings=AppSettings(online_intelligence_enabled=False),
    )
    try:
        window.rom_studio.store.create("About evidence project")
        window.nexus_events.start(
            source="ROM Studio",
            stage="about-evidence-test",
            title="Genuine local mission",
            summary="A producing subsystem wrote this event.",
            explanation="The About page may count it but cannot execute it.",
            next_action="Inspect the owning feature.",
        )

        window._navigate_route("about")
        app.processEvents()

        assert window.about_page.evidence_values["device"].text() == (
            f"{len(registry.packs)} DEVICE PACKS  •  1 OFFICIAL IDS"
        )
        assert window.about_page.evidence_values["knowledge"].text() == (
            "220 VERIFIED GUIDES  •  170 KNOWN FIXES"
        )
        ready_tools = sum(status.available for status in window.toolchain_center.statuses)
        tool_count = len(window.toolchain_center.statuses)
        assert window.about_page.evidence_values["build"].text() == (
            f"1 LOCAL PROJECT  •  {ready_tools}/{tool_count} HOST TOOLS READY"
        )
        assert window.about_page.evidence_values["live"].text() == ("1 GENUINE EVENT  •  1 ACTIVE")
        assert window.about_page.evidence_values["guardian"].text() == ("AUDIT + APPROVAL EVIDENCE")
        assert window.about_page.evidence_states["guardian"].text() == "VERIFY REQUIRED"
        assert window.about_page.evidence_cards["guardian"].property("evidenceState") == (
            "attention"
        )

        owners = {
            "device_atlas": window.device_packs_center,
            "archives": window.knowledge_center,
            "rom_studio": window.rom_studio,
            "forge_arsenal": window.toolchain_center,
            "live_console": window.live_console,
        }
        for route, owner in owners.items():
            window._navigate_route("about")
            window.about_page.evidence_buttons[route].click()
            app.processEvents()
            assert window.stack.currentWidget() is owner

        window._navigate_route("about")
        window.about_page.evidence_guide.click()
        app.processEvents()

        assert window.stack.currentWidget() is window.knowledge_center
        assert window.knowledge_center.list.currentItem().text() == (
            "About runtime evidence is stale or unavailable"
        )
        assert window.knowledge_center.source_context.property("source_route") == "about"
        assert not window.knowledge_center.source_context.isHidden()
        window.knowledge_center.source_return.click()
        app.processEvents()
        assert window.stack.currentWidget() is window.about_page
        assert window.guardian_center.worker is None

        trust_records = {
            "desktop-legal-publication-boundary": (
                "About contains Terms and Privacy drafts pending legal review"
            ),
            "desktop-local-privacy-boundary": (
                "About Privacy shows the real local and online data boundary"
            ),
            "desktop-licence-notice-inventory": (
                "Open-source licences or third-party notices are incomplete"
            ),
            "desktop-release-provenance": (
                "Changelog or installed Desktop build cannot prove what is running"
            ),
        }
        assert set(window.about_page.trust_buttons) == set(trust_records)
        for key, title in trust_records.items():
            window._navigate_route("about")
            window.about_page.trust_buttons[key].click()
            app.processEvents()
            assert window.stack.currentWidget() is window.knowledge_center
            assert window.knowledge_center.list.currentItem().text() == title
            assert window.knowledge_center.source_context.property("source_route") == "about"
            assert window.guardian_center.worker is None
            window.knowledge_center.source_return.click()
            app.processEvents()
            assert window.stack.currentWidget() is window.about_page

        window.nexus_events.path.write_text("{}", encoding="utf-8")
        window._navigate_route("about")
        app.processEvents()
        assert window.about_page.evidence_values["live"].text() == ("EVENT COUNTS UNAVAILABLE")
        assert window.about_page.evidence_cards["live"].property("evidenceState") == ("unavailable")
        assert "rejected the local ledger" in window.about_page.evidence_details["live"].text()
    finally:
        window.companion_center.transport.close()
        window.close()


def test_about_observes_guardian_verification_and_retires_stale_evidence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    started: list[object] = []
    monkeypatch.setattr("romverse.ui.guardian_center.start_background", started.append)
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(None, logo, tmp_path, app_icon_path=logo)
    try:
        window.guardian_center.refresh()
        assert len(started) == 1
        started[0].execute()
        app.processEvents()
        assert window.guardian_center.current_dashboard_state()[0] == "verified"

        window._navigate_route("about")
        app.processEvents()
        assert window.about_page.evidence_states["guardian"].text() == ("INTEGRITY VERIFIED")
        assert window.about_page.evidence_cards["guardian"].property("evidenceState") == "verified"

        audit = window.guardian_center.audit
        assert audit is not None
        audit.path.parent.mkdir(parents=True, exist_ok=True)
        audit.path.write_text("changed after About verification\n", encoding="utf-8")
        assert window.guardian_center.invalidate_dashboard_if_evidence_changed()
        app.processEvents()

        assert window.guardian_center.current_dashboard_state()[0] == "review_due"
        assert window.about_page.evidence_states["guardian"].text() == ("REVERIFY REQUIRED")
        assert window.about_page.evidence_cards["guardian"].property("evidenceState") == "attention"
        assert "EVIDENCE NEEDS ATTENTION" in window.about_page.runtime_scope.text()
        assert len(started) == 1
        assert window.guardian_center.worker is None

        window.about_page.evidence_buttons["guardian_core"].click()
        app.processEvents()
        assert window.stack.currentWidget() is window.guardian_center
    finally:
        window.companion_center.transport.close()
        window.close()


def test_opening_archives_reloads_new_private_synapse_learning(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(None, logo, tmp_path, app_icon_path=logo)
    try:
        store = window.knowledge_center.synapse_store
        assert isinstance(store, SynapseStore)
        scope = SynapseScope.create(
            operation="payload extraction",
            source_kind="payload-bin",
            device_codename="popsicle",
            tool_name="payload-dumper-go",
            tool_version="2.0.2",
        )

        def add(source: str) -> None:
            store.contribute(
                SynapseContribution.create(
                    fingerprint_id="a" * 64,
                    solution_id="inspect-payload-source",
                    scope=scope,
                    source_family=source,
                    summary="Verified typed payload inspection.",
                    successful=True,
                    locally_verified=True,
                    action_receipt_digest="b" * 64,
                    verification_evidence_digest="c" * 64,
                )
            )

        add("official-aosp")
        assert window.knowledge_center.synapse_knowledge == ()
        window._navigate_route("archives")
        app.processEvents()
        assert len(window.knowledge_center.synapse_knowledge) == 1
        assert window.knowledge_center.synapse_knowledge[0].state is (
            SynapseKnowledgeState.VERIFIED_SUCCESS
        )

        window._navigate_route("about")
        add("maintainer-tool")
        window._navigate_route("archives")
        app.processEvents()
        assert window.knowledge_center.synapse_knowledge[0].state is (SynapseKnowledgeState.STRONG)
        assert "1 USABLE" in window.knowledge_center.learning_status.text()
        window.knowledge_center.learning_button.click()
        app.processEvents()
        assert window.knowledge_center.learning_dialog is not None
        assert "2 successful verification(s)" in (
            window.knowledge_center.learning_dialog.detail.toPlainText()
        )
        assert window.guardian_center.worker is None
    finally:
        if window.knowledge_center.learning_dialog is not None:
            window.knowledge_center.learning_dialog.close()
        window.companion_center.transport.close()
        window.close()


def test_command_deck_cards_are_context_aware_and_route_to_canonical_pages(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(None, logo, tmp_path, app_icon_path=logo)
    try:
        actions = window.device_center.quick_action_buttons
        assert set(actions) == {
            "Build ROM",
            "Device DNA",
            "Pre-Build Simulation",
            "Recipes",
            "Health Review",
            "Repair Phone",
            "Guardian",
            "Rescue & Backup",
            "Timeline",
            "Live Operations",
            "Wireless Transfer",
            "ROMVERSE Lab",
        }
        assert "CREATE PROJECT" in actions["Build ROM"].text()
        assert "NEEDS FIRMWARE" in actions["Pre-Build Simulation"].text()
        assert not actions["ROMVERSE Lab"].isHidden()

        window.device_center.set_workspace_context("Project Orion", True)
        actions = window.device_center.quick_action_buttons
        assert "CONTINUE PROJECT" in actions["Build ROM"].text()
        assert "READY" in actions["Pre-Build Simulation"].text()
        assert any(
            "Project Orion" in label.text()
            for label in window.device_center.body_content.findChildren(
                type(window.device_center.next_title)
            )
        )

        genesis_opened = []
        monkeypatch.setattr(
            window.rom_studio,
            "_open_guided_setup",
            lambda: genesis_opened.append(True),
        )
        window.device_center.flight_plan_button.click()
        app.processEvents()
        assert window.stack.currentWidget() is window.rom_studio
        assert genesis_opened == [True]
        assert not window.rom_studio.dashboard_handoff.isHidden()
        assert window.rom_studio.dashboard_handoff_title.text() == ("Build ROM → Genesis Sequence")
        assert "NO BUILD OR PHONE ACTION STARTED" in (
            window.rom_studio.dashboard_handoff_detail.text()
        )

        window._navigate(0)
        actions["Build ROM"].click()
        app.processEvents()
        assert window.stack.currentWidget() is window.rom_studio
        assert genesis_opened == [True, True]

        window._navigate(0)
        actions["Pre-Build Simulation"].click()
        app.processEvents()
        assert window.stack.currentWidget() is window.rom_studio
        assert window.rom_studio.command_tabs.currentIndex() == 1
        assert window.rom_studio.dashboard_handoff_title.text() == (
            "Pre-Build Simulation → Build & Proof"
        )
        assert window.rom_studio.dashboard_handoff_badge.text() == "PREREQUISITE"
        assert "NO BUILD OR PHONE ACTION STARTED" in (
            window.rom_studio.dashboard_handoff_detail.text()
        )
        assert window.rom_studio.worker is None

        window._navigate(0)
        actions["Recipes"].click()
        app.processEvents()
        assert window.stack.currentWidget() is window.rom_studio
        assert window.rom_studio.command_tabs.currentIndex() == 2
        assert window.rom_studio.dashboard_handoff_title.text() == "Recipes → Recipe Forge"
        assert "NO RECIPE OR PHONE ACTION STARTED" in (
            window.rom_studio.dashboard_handoff_detail.text()
        )
        assert window.rom_studio.worker is None

        window._navigate(0)
        window._handle_dashboard_action("Optimize")
        app.processEvents()
        assert window.stack.currentWidget() is window.diagnostics_center

        window._navigate(0)
        actions["Guardian"].click()
        app.processEvents()
        assert window.stack.currentIndex() == 3
        assert not window.guardian_center.dashboard_handoff.isHidden()
        assert window.guardian_center.dashboard_handoff_badge.text() == "VERIFY REQUIRED"
        guardian_action = window.device_center.quick_action_buttons["Guardian"]
        assert guardian_action.text().splitlines()[1] == "VERIFY REQUIRED"
        assert guardian_action.property("evidenceReady") is False
        window.guardian_center._publish_dashboard_state(
            "verified",
            "SHA-256 audit chain verified across current operation evidence.",
            True,
        )
        assert guardian_action.text().splitlines()[1] == "INTEGRITY VERIFIED"
        assert guardian_action.property("evidenceReady") is True
        assert window.guardian_center.dashboard_handoff_badge.text() == ("INTEGRITY VERIFIED")
        window._navigate(0)
        window.device_center.quick_action_buttons["Wireless Transfer"].click()
        app.processEvents()
        assert window.stack.currentIndex() == window.companion_index

        window._navigate(0)
        window._handle_dashboard_action("View Activity Center")
        app.processEvents()
        assert window.stack.currentWidget() is window.activity_center

        window._navigate(0)
        lab = window.device_center.quick_action_buttons["ROMVERSE Lab"]
        lab.click()
        app.processEvents()
        assert window.stack.currentWidget() is window.nexus_center
    finally:
        window.companion_center.transport.close()
        window.close()


def test_command_deck_evidence_handoffs_preserve_current_owner_state(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
    window = MainWindow(
        None,
        logo,
        tmp_path,
        app_icon_path=logo,
        pack_registry=registry,
        app_settings=AppSettings(online_intelligence_enabled=False),
    )
    owners = (
        ("Device DNA", window.device_packs_center),
        ("Health Review", window.diagnostics_center),
        ("Rescue & Backup", window.backup_center),
    )
    try:
        for action, owner in owners:
            window._navigate(0)
            window._handle_dashboard_action(action)
            app.processEvents()
            assert window.stack.currentWidget() is owner
            assert not owner.dashboard_handoff.isHidden()
            assert owner.dashboard_handoff_badge.text() == "EVIDENCE NEEDED"
            assert "NO " in owner.dashboard_handoff_detail.text()
            assert not owner.open_dashboard_intent("Unknown workflow")

        device = _device()
        window._scan_complete([device])
        app.processEvents()
        assert window.device_packs_center.active_report is not None
        assert window.diagnostics_center.current_report is not None
        assert window.backup_center.device is not None

        window._navigate(0)
        window._handle_dashboard_action("Device DNA")
        app.processEvents()
        report = window.device_packs_center.active_report
        assert report is not None
        assert window.stack.currentWidget() is window.device_packs_center
        assert window.device_packs_center.dashboard_handoff_badge.text() == "CURRENT EVIDENCE"
        assert report.report_digest[:16] in (
            window.device_packs_center.dashboard_handoff_detail.text()
        )
        assert "NO SCAN, APPROVAL, BUILD, FLASH, OR PHONE ACTION STARTED" in (
            window.device_packs_center.dashboard_handoff_detail.text()
        )

        window._navigate(0)
        window._handle_dashboard_action("Health Review")
        app.processEvents()
        diagnostic = window.diagnostics_center.current_report
        assert diagnostic is not None
        assert window.stack.currentWidget() is window.diagnostics_center
        assert (
            str(diagnostic.health_score) in window.diagnostics_center.dashboard_handoff_title.text()
        )
        assert "Recommended Action Plan" in (
            window.diagnostics_center.dashboard_handoff_detail.text()
        )
        assert "NO NEW SCAN, OPTIMIZATION, CLEANUP, OR PHONE ACTION STARTED" in (
            window.diagnostics_center.dashboard_handoff_detail.text()
        )

        window._navigate(0)
        window._handle_dashboard_action("Rescue & Backup")
        app.processEvents()
        assert window.stack.currentWidget() is window.backup_center
        assert window.backup_center.dashboard_handoff_badge.text() == "PLAN RECOVERY"
        assert window.backup_center.device.display_name in (
            window.backup_center.dashboard_handoff_title.text()
        )
        assert "NO BACKUP, COPY, RESTORE, OR PHONE ACTION STARTED" in (
            window.backup_center.dashboard_handoff_detail.text()
        )
        assert window.active_worker is None
        assert window.backup_center.worker is None
        assert window.backup_center.evidence_worker is None
        assert window.backup_center.media_backup_worker is None
    finally:
        window.companion_center.transport.close()
        window.close()


def test_device_atlas_and_nexus_preserve_exact_context_into_rom_studio(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
    window = MainWindow(
        None,
        logo,
        tmp_path,
        app_icon_path=logo,
        pack_registry=registry,
        app_settings=AppSettings(online_intelligence_enabled=False),
    )
    genesis_opened: list[bool] = []
    monkeypatch.setattr(
        window.rom_studio,
        "_open_guided_setup",
        lambda: genesis_opened.append(True),
    )
    try:
        window._scan_complete([_device()])
        app.processEvents()
        report = window.device_packs_center.active_report
        assert report is not None and report.build_contract_ready

        window._navigate_route("device_atlas")
        window.device_packs_center.rom_studio_requested.emit(report.report_id, "0" * 64)
        app.processEvents()
        assert window.stack.currentWidget() is window.device_packs_center
        assert "NEXT ACTION STOPPED" in window.device_packs_center.next_action_feedback.text()
        assert "Start ROM Mission no longer matches" in (
            window.device_packs_center.next_action_feedback.text()
        )
        assert window.rom_studio.worker is None

        window.device_packs_center.continue_button.click()
        app.processEvents()
        assert window.stack.currentWidget() is window.rom_studio
        assert genesis_opened == [True]
        assert window.rom_studio.dashboard_handoff_eyebrow.text().startswith("DEVICE ATLAS HANDOFF")
        assert report.report_digest[:16] in window.rom_studio.dashboard_handoff_detail.text()
        assert "NO BUILD, APPROVAL, FLASH, OR PHONE ACTION STARTED" in (
            window.rom_studio.dashboard_handoff_detail.text()
        )
        assert window.rom_studio.worker is None

        window._navigate_route("device_atlas")
        window.device_packs_center.requirement_buttons["build"].click()
        app.processEvents()
        assert window.stack.currentWidget() is window.rom_studio
        assert genesis_opened == [True]
        assert window.rom_studio.command_tabs.currentIndex() == 1
        assert window.rom_studio.dashboard_handoff_title.text() == ("Device Atlas → Build & Proof")
        assert window.rom_studio.worker is None

        project = window.rom_studio.store.create("Nexus exact project")
        window.nexus_center.refresh()
        window._navigate_route("nexus")
        window.nexus_center.evidence_studio_button.click()
        app.processEvents()
        assert window.stack.currentWidget() is window.rom_studio
        assert window.rom_studio.current_project is not None
        assert window.rom_studio.current_project.project_id == project.project_id
        assert window.rom_studio.dashboard_handoff_eyebrow.text().startswith(
            "ROMVERSE NEXUS HANDOFF"
        )
        assert project.project_id in window.rom_studio.dashboard_handoff_detail.text()
        assert "NO PROJECT WORKER, PLAN, BUILD, OR PHONE ACTION STARTED" in (
            window.rom_studio.dashboard_handoff_detail.text()
        )
        assert window.rom_studio.worker is None
    finally:
        window.companion_center.transport.close()
        window.close()


def test_device_atlas_starts_genesis_with_identity_evidence_before_build_is_ready(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
    window = MainWindow(
        None,
        logo,
        tmp_path,
        app_icon_path=logo,
        pack_registry=registry,
        app_settings=AppSettings(online_intelligence_enabled=False),
    )
    genesis_opened: list[bool] = []
    monkeypatch.setattr(
        window.rom_studio,
        "_open_guided_setup",
        lambda: genesis_opened.append(True),
    )
    try:
        window._scan_complete(
            [
                AndroidDevice(
                    "private-pixel",
                    DeviceState.DEVICE,
                    manufacturer="Google",
                    brand="google",
                    model="Pixel 9 Pro",
                    product="caiman",
                    codename="caiman",
                    android_version="16",
                )
            ]
        )
        app.processEvents()
        report = window.device_packs_center.active_report
        assert report is not None and not report.build_contract_ready
        assert not window.device_packs_center.continue_button.isHidden()
        assert window.device_packs_center.active_knowledge_device_serial == "private-pixel"
        assert window.device_packs_center.active_knowledge_report is not None
        assert window.device_packs_center.passport_knowledge.text() != (
            "Matching current evidence…"
        )

        window._navigate_route("device_atlas")
        window.device_packs_center.continue_button.click()
        app.processEvents()

        assert window.stack.currentWidget() is window.rom_studio
        assert genesis_opened == [True]
        assert window.rom_studio.dashboard_handoff_badge.text() == (
            "BUILD EVIDENCE NEEDED • FLASH LOCKED"
        )
        assert "NO BUILD, APPROVAL, FLASH, OR PHONE ACTION STARTED" in (
            window.rom_studio.dashboard_handoff_detail.text()
        )
        assert window.rom_studio.worker is None
    finally:
        window.companion_center.transport.close()
        window.close()


def test_device_atlas_rom_mission_preserves_current_device_intelligence_and_owner_return(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    store, registry, project, _report = _project(tmp_path)
    window = MainWindow(
        None,
        logo,
        store.workspace,
        app_icon_path=logo,
        pack_registry=registry,
        app_settings=AppSettings(online_intelligence_enabled=False),
    )
    opened_contexts = []
    monkeypatch.setattr(
        window.rom_studio,
        "_open_guided_setup",
        lambda: opened_contexts.append(window.rom_studio.guided_context()),
    )
    phone = _device(serial="CURRENT-PHONE-9042")
    try:
        window.rom_studio.refresh(project.project_id)
        window._scan_complete([phone])
        app.processEvents()

        profile = window.rom_studio.device_dna.profiles.load(project.project_id)
        matrix = window.rom_studio.compatibility.matrices.load(project.project_id)
        report = window.device_packs_center.active_report
        assert profile is not None
        assert matrix is not None
        assert matrix.device_dna_digest == profile.profile_digest
        assert matrix.decision("guardian_flash").status.value == "Unknown"
        assert report is not None

        window._navigate_route("device_atlas")
        window.device_packs_center.continue_button.click()
        app.processEvents()

        assert window.stack.currentWidget() is window.rom_studio
        assert len(opened_contexts) == 1
        context = opened_contexts[0]
        assert context.device is not None and context.device.serial == phone.serial
        assert context.device_pack_id == report.pack_id
        assert any(profile.profile_digest[:16] in item for item in context.device_dna_evidence)
        assert any("Guardian Flash: Unknown" in item for item in context.device_dna_evidence)
        assert phone.masked_serial() in window.rom_studio.dashboard_handoff_detail.text()
        assert profile.profile_digest[:16] in window.rom_studio.dashboard_handoff_detail.text()
        assert "Compatibility Unknown" in window.rom_studio.dashboard_handoff_detail.text()
        assert "NO BUILD, APPROVAL, FLASH, OR PHONE ACTION STARTED" in (
            window.rom_studio.dashboard_handoff_detail.text()
        )
        assert window.rom_studio.worker is None

        assert window.rom_studio.request_device_atlas()
        app.processEvents()
        assert window.stack.currentWidget() is window.device_packs_center
        assert window.device_packs_center.active_device == phone
        assert window.device_packs_center.active_pack is not None
        assert window.device_packs_center.active_pack.pack_id == report.pack_id
        assert window.device_packs_center.active_report == report
        assert window.device_packs_center.active_device_dna == profile
        assert window.rom_studio.worker is None

        substitute = replace(phone, serial="SUBSTITUTE-PHONE-1188")
        window.device_packs_center.active_device = substitute
        window.rom_studio.devices = [substitute]
        window.device_packs_center.rom_studio_requested.emit(
            report.report_id,
            report.report_digest,
        )
        app.processEvents()
        assert window.stack.currentWidget() is window.device_packs_center
        assert len(opened_contexts) == 1
        assert "ROM Studio rejected changed or invalid Device Atlas evidence" in (
            window.device_packs_center.next_action_feedback.text()
        )
        assert window.rom_studio.worker is None
    finally:
        window.companion_center.transport.close()
        window.close()


def test_device_atlas_rom_mission_selects_the_one_matching_saved_project(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    store, registry, matching_project, _report = _project(tmp_path)
    unrelated_project = store.create("Unrelated project", "another.device.pack")
    window = MainWindow(
        None,
        logo,
        store.workspace,
        app_icon_path=logo,
        pack_registry=registry,
        app_settings=AppSettings(online_intelligence_enabled=False),
    )
    opened_contexts = []
    monkeypatch.setattr(
        window.rom_studio,
        "_open_guided_setup",
        lambda: opened_contexts.append(window.rom_studio.guided_context()),
    )
    phone = _device(serial="CURRENT-PHONE-2764")
    try:
        window.rom_studio.refresh(unrelated_project.project_id)
        assert window.rom_studio.current_project == unrelated_project
        window._scan_complete([phone])
        app.processEvents()

        report = window.device_packs_center.active_report
        assert report is not None
        assert report.pack_id == matching_project.device_pack_id
        window._navigate_route("device_atlas")
        window.device_packs_center.continue_button.click()
        app.processEvents()

        assert window.stack.currentWidget() is window.rom_studio
        assert window.rom_studio.current_project is not None
        assert window.rom_studio.current_project.project_id == matching_project.project_id
        assert len(opened_contexts) == 1
        context = opened_contexts[0]
        assert context.device is not None and context.device.serial == phone.serial
        assert context.device_pack_id == report.pack_id
        assert any("Guardian Flash: Unknown" in item for item in context.device_dna_evidence)
        assert matching_project.name in window.rom_studio.dashboard_handoff_detail.text()
        assert unrelated_project.name not in window.rom_studio.dashboard_handoff_detail.text()
        assert "NO BUILD, APPROVAL, FLASH, OR PHONE ACTION STARTED" in (
            window.rom_studio.dashboard_handoff_detail.text()
        )
        assert window.rom_studio.worker is None
    finally:
        window.companion_center.transport.close()
        window.close()


def test_device_atlas_rom_mission_requires_choice_between_matching_saved_projects(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    store, registry, selected_project, _report = _project(tmp_path)
    second_match = store.create("Second matching project", selected_project.device_pack_id)
    unrelated_project = store.create("Unrelated project", "another.device.pack")
    window = MainWindow(
        None,
        logo,
        store.workspace,
        app_icon_path=logo,
        pack_registry=registry,
        app_settings=AppSettings(online_intelligence_enabled=False),
    )
    opened_contexts = []
    choices = []

    def choose_project(_parent, title, prompt, items, _current, _editable):
        choices.append((title, prompt, tuple(items)))
        selected = next(item for item in items if selected_project.project_id in item)
        return selected, True

    monkeypatch.setattr("romverse.ui.main_window.QInputDialog.getItem", choose_project)
    monkeypatch.setattr(
        window.rom_studio,
        "_open_guided_setup",
        lambda: opened_contexts.append(window.rom_studio.guided_context()),
    )
    phone = _device(serial="CURRENT-PHONE-4671")
    try:
        window.rom_studio.refresh(unrelated_project.project_id)
        window._scan_complete([phone])
        app.processEvents()
        report = window.device_packs_center.active_report
        assert report is not None

        window._navigate_route("device_atlas")
        window.device_packs_center.continue_button.click()
        app.processEvents()

        assert choices and choices[0][0] == "Choose ROM Mission project"
        assert selected_project.project_id in " ".join(choices[0][2])
        assert second_match.project_id in " ".join(choices[0][2])
        assert window.stack.currentWidget() is window.rom_studio
        assert window.rom_studio.current_project is not None
        assert window.rom_studio.current_project.project_id == selected_project.project_id
        assert len(opened_contexts) == 1
        assert opened_contexts[0].device is not None
        assert opened_contexts[0].device.serial == phone.serial
        assert opened_contexts[0].device_pack_id == report.pack_id
        assert window.rom_studio.worker is None

        window.rom_studio.refresh(unrelated_project.project_id)
        window._navigate_route("device_atlas")
        monkeypatch.setattr(
            "romverse.ui.main_window.QInputDialog.getItem",
            lambda *_args: ("", False),
        )
        window.device_packs_center.continue_button.click()
        app.processEvents()

        assert window.stack.currentWidget() is window.device_packs_center
        assert window.rom_studio.current_project is not None
        assert window.rom_studio.current_project.project_id == unrelated_project.project_id
        assert len(opened_contexts) == 1
        assert "Project choice cancelled" in (
            window.device_packs_center.next_action_feedback.text()
        )
        assert window.rom_studio.worker is None
    finally:
        window.companion_center.transport.close()
        window.close()


def test_device_atlas_zero_match_opens_transient_new_project_mission_and_cancels_cleanly(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    fixture_root = tmp_path / "pack-fixture"
    fixture_root.mkdir()
    _fixture_store, registry, _fixture_project, _report = _project(fixture_root)
    store = RomProjectStore(tmp_path / "workspace")
    unrelated_project = store.create("Preserved unrelated project", "another.device.pack")
    window = MainWindow(
        None,
        logo,
        store.workspace,
        app_icon_path=logo,
        pack_registry=registry,
        app_settings=AppSettings(online_intelligence_enabled=False),
    )
    missions = []

    def capture_mission(mission):
        missions.append(mission)
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(
        "romverse.ui.guided_mission.GuidedBuildMission.exec",
        capture_mission,
    )
    phone = _device(serial="CURRENT-PHONE-8390")
    try:
        window.rom_studio.refresh(unrelated_project.project_id)
        original_projects = store.list_projects()
        window._scan_complete([phone])
        app.processEvents()
        report = window.device_packs_center.active_report
        assert report is not None
        assert not any(project.device_pack_id == report.pack_id for project in original_projects)

        window._navigate_route("device_atlas")
        window.device_packs_center.continue_button.click()
        app.processEvents()

        assert window.stack.currentWidget() is window.rom_studio
        assert len(missions) == 1
        mission = missions[0]
        assert mission.assessments[0].stage.action == "new-project"
        assert mission.selected_index == 0
        context = mission._context()
        assert not context.project_exists
        assert context.device is not None and context.device.serial == phone.serial
        assert context.device_pack_id == report.pack_id
        assert mission.firmware_identity_title.text() == "No firmware selected"
        assert unrelated_project.name not in mission.firmware_identity_detail.text()
        assert mission.compatibility_title.text() == "AWAITING COMPARISON"
        assert mission.compatibility_detail.text() == "Add firmware and a live device"
        assert window.rom_studio.current_project == unrelated_project
        assert store.list_projects() == original_projects
        assert window.rom_studio.worker is None

        monkeypatch.setattr(
            "romverse.ui.rom_studio.ProjectNameDialog.exec",
            lambda _dialog: QDialog.DialogCode.Rejected,
        )
        mission._run_stage()
        app.processEvents()
        mission.close()
        app.processEvents()

        assert window.rom_studio.current_project == unrelated_project
        assert store.list_projects() == original_projects
        assert not (
            store.projects_root / unrelated_project.project_id / "guided-mission.json"
        ).exists()
        assert window.rom_studio.request_device_atlas()
        app.processEvents()
        assert window.stack.currentWidget() is window.device_packs_center
        assert window.rom_studio.current_project == unrelated_project
        assert window.rom_studio.worker is None
    finally:
        window.companion_center.transport.close()
        window.close()


def test_rom_studio_preserves_exact_project_into_time_machine_and_device_atlas(
    tmp_path: Path,
) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    store, registry, project, _report = _project(tmp_path)
    store.create_working_copy(project.project_id)
    snapshot = store.create_snapshot(project.project_id)
    window = MainWindow(
        None,
        logo,
        store.workspace,
        app_icon_path=logo,
        pack_registry=registry,
        app_settings=AppSettings(online_intelligence_enabled=False),
    )
    try:
        window._scan_complete([_device()])
        app.processEvents()
        window.rom_studio.refresh(project.project_id)
        assert window.rom_studio.current_project is not None

        window.rom_studio.rollback_button.click()
        app.processEvents()
        assert window.stack.currentWidget() is window.backup_center
        assert str(window.backup_center.project_selector.currentData()) == project.project_id
        assert window.backup_center.snapshot_list.currentItem() is not None
        assert snapshot.snapshot_id in window.backup_center.snapshot_list.currentItem().text()
        assert window.backup_center.dashboard_handoff_eyebrow.text().startswith(
            "ROM STUDIO HANDOFF"
        )
        assert project.project_id in window.backup_center.dashboard_handoff_detail.text()
        assert project.original.sha256[:16] in window.backup_center.dashboard_handoff_detail.text()
        assert "NO BACKUP, COPY, RESTORE, BUILD, FLASH, OR PHONE ACTION STARTED" in (
            window.backup_center.dashboard_handoff_detail.text()
        )
        assert window.backup_center.worker is None

        window._navigate_route("rom_studio")
        assert window.rom_studio.request_device_atlas()
        app.processEvents()
        assert window.stack.currentWidget() is window.device_packs_center
        assert window.device_packs_center.dashboard_handoff_eyebrow.text().startswith(
            "ROM STUDIO HANDOFF"
        )
        assert project.project_id in window.device_packs_center.dashboard_handoff_detail.text()
        assert project.original.sha256[:16] in (
            window.device_packs_center.dashboard_handoff_detail.text()
        )
        assert window.device_packs_center.dashboard_handoff_badge.text() == (
            "CURRENT • GATES REMAIN"
        )
        assert window.device_packs_center.active_report.report_digest[:16] in (
            window.device_packs_center.dashboard_handoff_detail.text()
        )
        assert "build LOCKED" in window.device_packs_center.dashboard_handoff_detail.text()
        assert "NO SCAN, BUILD, APPROVAL, FLASH, OR PHONE ACTION STARTED" in (
            window.device_packs_center.dashboard_handoff_detail.text()
        )

        window._navigate_route("rom_studio")
        window._open_time_machine("missing-project")
        assert window.stack.currentWidget() is window.rom_studio
        assert "TIME MACHINE HANDOFF STOPPED" in window.rom_studio.operation_status.text()
        window._open_device_atlas_from_studio("missing-project")
        assert window.stack.currentWidget() is window.rom_studio
        assert "DEVICE ATLAS HANDOFF STOPPED" in window.rom_studio.operation_status.text()
    finally:
        window.companion_center.transport.close()
        window.close()


def test_device_atlas_project_requirements_connect_back_to_exact_studio_and_forge(
    tmp_path: Path,
) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Current HyperOS project", "xiaomi.hyperos")
    source = _source(
        tmp_path,
        "popsicle-ota_full-OS4.0.0.25.XPBCNXM-user-17.0-test.zip",
    )
    project = store.import_original(project.project_id, source)
    tree = store.working_root / project.project_id / "tree"
    tree.mkdir(parents=True)
    (tree / "payload.bin").write_bytes(b"CrAU current payload")
    payload_dumper = tmp_path / "payload-dumper-go"
    payload_dumper.write_bytes(b"verified test executable")
    statuses = (
        ToolStatus("Python", True, "/verified/python", "test", "Ready"),
        ToolStatus("Payload Dumper", True, str(payload_dumper), "test", "Ready"),
        ToolStatus("AVBTool", True, "/verified/avbtool", "test", "Ready"),
    )
    source_blueprint = FirmwareSourceIntelligenceService(
        store,
        statuses,
        SourceRunner(),
    ).prepare(project.project_id)
    window = MainWindow(
        None,
        logo,
        store.workspace,
        app_icon_path=logo,
        pack_registry=registry,
        app_settings=AppSettings(online_intelligence_enabled=False),
    )
    try:
        window.rom_studio.set_tool_statuses(statuses)
        window.device_packs_center.set_tool_statuses(statuses)
        window._scan_complete([_device()])
        window.rom_studio.refresh(project.project_id)
        app.processEvents()

        assert window.rom_studio.request_device_atlas()
        app.processEvents()
        blueprint = window.device_packs_center.current_requirements()
        assert blueprint is not None and blueprint.project_scoped
        assert blueprint.project_id == project.project_id
        assert blueprint.source_blueprint_digest == source_blueprint.blueprint_digest
        assert blueprint.source_required_tools == ("Python", "Payload Dumper", "AVBTool")
        compile_lane = blueprint.lane("compile")
        assert compile_lane is not None and compile_lane.route == "forge_arsenal_project"

        window.device_packs_center.requirement_buttons["compile"].click()
        app.processEvents()
        assert window.stack.currentWidget() is window.toolchain_center
        context = window.toolchain_center._studio_project_context
        assert context is not None
        assert context.project_id == project.project_id
        assert context.source_sha256 == project.original.sha256
        assert context.source_blueprint_digest == source_blueprint.blueprint_digest
        assert context.required_tools == ("Python", "Payload Dumper", "AVBTool")
        assert not context.build_contract_bound
        assert "project-local ota-payload blueprint" in (
            window.toolchain_center.device_pack_handoff_detail.text().casefold()
        )

        window._navigate_route("rom_studio")
        assert window.rom_studio.request_device_atlas()
        app.processEvents()
        window.device_packs_center.requirement_buttons["build"].click()
        app.processEvents()
        assert window.stack.currentWidget() is window.rom_studio
        assert window.rom_studio.current_project is not None
        assert window.rom_studio.current_project.project_id == project.project_id
        assert window.rom_studio.dashboard_handoff_title.text() == (
            "Device Atlas → project Build & Proof"
        )
        assert source_blueprint.blueprint_digest[:16] in (
            window.rom_studio.dashboard_handoff_detail.text()
        )
        assert "flash authority NONE" in window.rom_studio.dashboard_handoff_detail.text()
        assert window.rom_studio.worker is None
    finally:
        window.companion_center.transport.close()
        window.close()


def test_command_deck_primary_rom_action_uses_shared_exact_device_mission_context(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    store, registry, matching_project, _report = _project(tmp_path)
    unrelated_project = store.create("Unrelated Command Deck project", "another.device.pack")
    window = MainWindow(
        None,
        logo,
        store.workspace,
        app_icon_path=logo,
        pack_registry=registry,
        app_settings=AppSettings(online_intelligence_enabled=False),
    )
    opened_contexts = []
    monkeypatch.setattr(
        window.rom_studio,
        "_open_guided_setup",
        lambda: opened_contexts.append(window.rom_studio.guided_context()),
    )
    phone = _device(serial="COMMAND-DECK-PHONE-5187")
    try:
        window.rom_studio.refresh(unrelated_project.project_id)
        window._scan_complete([phone])
        app.processEvents()
        report = window.device_packs_center.active_report
        assert report is not None
        assert window.stack.currentWidget() is window.device_center

        window.device_center.primary_action_buttons["Start ROM Project"].click()
        app.processEvents()

        assert window.stack.currentWidget() is window.rom_studio
        assert window.rom_studio.current_project is not None
        assert window.rom_studio.current_project.project_id == matching_project.project_id
        assert len(opened_contexts) == 1
        context = opened_contexts[0]
        assert context.device is not None and context.device.serial == phone.serial
        assert context.device_pack_id == report.pack_id
        profile = window.rom_studio.device_dna.profiles.load(matching_project.project_id)
        matrix = window.rom_studio.compatibility.matrices.load(matching_project.project_id)
        assert profile is not None and matrix is not None
        assert matrix.device_dna_digest == profile.profile_digest
        assert matrix.decision("guardian_flash").status.value == "Unknown"
        assert any(profile.profile_digest[:16] in item for item in context.device_dna_evidence)
        assert any("Guardian Flash: Unknown" in item for item in context.device_dna_evidence)
        assert matching_project.name in window.rom_studio.dashboard_handoff_detail.text()
        assert unrelated_project.name not in window.rom_studio.dashboard_handoff_detail.text()
        assert window.rom_studio.worker is None
    finally:
        window.companion_center.transport.close()
        window.close()


def test_rom_studio_command_deck_device_evidence_round_trip_is_exact(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    store, registry, project, _report = _project(tmp_path)
    window = MainWindow(None, logo, store.workspace, app_icon_path=logo, pack_registry=registry)
    scans: list[bool] = []
    monkeypatch.setattr(window, "scan", lambda: scans.append(True))
    try:
        window.rom_studio.set_devices([_device()])
        window.device_center.set_devices([_device()])
        window.rom_studio.refresh(project.project_id)
        app.processEvents()

        assert window.rom_studio.request_device_center("build-readiness")
        app.processEvents()
        assert window.stack.currentWidget() is window.device_center
        assert window.device_center.studio_handoff.isVisibleTo(window.device_center)
        assert window.device_center.studio_handoff_badge.text() == ("TARGET MATCH • READ ONLY")
        assert project.project_id in window.device_center.studio_handoff_detail.text()
        assert project.original is not None
        assert project.original.sha256[:16] in window.device_center.studio_handoff_detail.text()

        window.device_center.studio_return_button.click()
        app.processEvents()
        assert window.stack.currentWidget() is window.rom_studio
        assert window.rom_studio.current_project is not None
        assert window.rom_studio.current_project.project_id == project.project_id
        assert window.rom_studio.dashboard_handoff_eyebrow.text().startswith("COMMAND DECK HANDOFF")
        assert "Forge Control device prerequisite" in (
            window.rom_studio.dashboard_handoff_detail.text()
        )
        assert window.rom_studio.command_tabs.currentIndex() == 1
        assert window.rom_studio.worker is None

        assert window.rom_studio.request_device_center("ascension-refresh")
        app.processEvents()
        assert window.stack.currentWidget() is window.device_center
        assert scans == [True]
        assert "Ascension requested a fresh read-only target check" in (
            window.device_center.studio_handoff_title.text()
        )

        window.device_center.rom_studio_requested.emit(
            project.project_id,
            "0" * 64,
            "ascension-refresh",
        )
        app.processEvents()
        assert window.stack.currentWidget() is window.device_center
        assert window.device_center.studio_handoff_badge.text() == "CONTEXT REFUSED"
        assert "NO SCAN, PROJECT WORKER, BUILD, ROOT, FLASH" in (
            window.device_center.studio_handoff_detail.text()
        )
    finally:
        window.companion_center.transport.close()
        window.close()


def test_rom_studio_forge_tool_evidence_round_trip_is_exact(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    store, registry, project, report = _project(tmp_path)
    window = MainWindow(None, logo, store.workspace, app_icon_path=logo, pack_registry=registry)
    try:
        window.rom_studio.refresh(project.project_id)
        app.processEvents()

        assert window.rom_studio.request_toolchain()
        app.processEvents()
        assert window.stack.currentWidget() is window.toolchain_center
        context = window.toolchain_center._studio_project_context
        assert context is not None
        assert context.project_id == project.project_id
        assert project.original is not None
        assert context.source_sha256 == project.original.sha256
        assert context.inspection_digest == report.record_digest
        assert context.build_contract_bound
        assert project.project_id in window.toolchain_center.device_pack_handoff_detail.text()
        assert project.original.sha256[:16] in (
            window.toolchain_center.device_pack_handoff_detail.text()
        )
        assert "BUILD / PHONE AUTHORITY: NONE" in (
            window.toolchain_center.device_pack_handoff_feedback.text()
        )
        assert window.toolchain_center.context_continue_button.isEnabled()

        window.toolchain_center.context_guide_button.click()
        app.processEvents()
        assert window.stack.currentWidget() is window.knowledge_center
        assert window.knowledge_center.list.currentItem().text() == (
            "ROM Studio prerequisite route loses the exact project or does not refresh evidence"
        )
        window.knowledge_center.source_return.click()
        app.processEvents()
        assert window.stack.currentWidget() is window.toolchain_center

        window.toolchain_center.context_continue_button.click()
        app.processEvents()
        assert window.stack.currentWidget() is window.rom_studio
        assert window.rom_studio.current_project is not None
        assert window.rom_studio.current_project.project_id == project.project_id
        assert window.rom_studio.dashboard_handoff_eyebrow.text().startswith(
            "FORGE ARSENAL HANDOFF"
        )
        assert context.context_digest[:16] in window.rom_studio.dashboard_handoff_detail.text()
        assert "NO PROJECT WORKER, BUILD, ROOT, APPROVAL, FLASH" in (
            window.rom_studio.dashboard_handoff_detail.text()
        )
        assert window.rom_studio.command_tabs.currentIndex() == 1
        assert window.rom_studio.worker is None

        assert window.rom_studio.request_toolchain()
        app.processEvents()
        window.toolchain_center.studio_project_continue_requested.emit(
            project.project_id,
            "0" * 64,
        )
        app.processEvents()
        assert window.stack.currentWidget() is window.toolchain_center
        assert "STALE PROJECT CONTEXT" in (window.toolchain_center.device_pack_handoff_badge.text())
        assert "NO INSTALL, PROJECT WORKER, BUILD, ROOT, FLASH" in (
            window.toolchain_center.device_pack_handoff_feedback.text()
        )
    finally:
        window.companion_center.transport.close()
        window.close()


def test_studio_manifest_opens_persistent_guardian_context_and_returns_exactly(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    store, project, registry, report, device = _prepared_guardian_manifest(tmp_path)
    manifest = GuardianManifestReviewService(store, registry).compile(
        project.project_id,
        report,
        device,
    )
    window = MainWindow(
        None,
        logo,
        store.workspace,
        app_icon_path=logo,
        pack_registry=registry,
        app_settings=AppSettings(online_intelligence_enabled=False),
    )
    monkeypatch.setattr(
        "romverse.ui.main_window.BuildReadinessService.assess",
        lambda *_args, **_kwargs: report,
    )
    try:
        window.rom_studio.set_devices([device])
        window.rom_studio.guardian_review_requested.emit(
            project.project_id,
            manifest.manifest_digest,
        )
        app.processEvents()

        assert window.stack.currentWidget() is window.guardian_center
        assert window.guardian_center.studio_review_identity == (
            project.project_id,
            manifest.manifest_digest,
        )
        assert manifest.manifest_digest[:16] in (window.guardian_center.studio_review_detail.text())
        assert window.guardian_center.studio_review_badge.text() == "ZERO AUTHORITY"
        assert window.guardian_center.worker is None

        window.guardian_center.studio_return_button.click()
        app.processEvents()
        assert window.stack.currentWidget() is window.rom_studio
        assert window.rom_studio.current_project is not None
        assert window.rom_studio.current_project.project_id == project.project_id
        assert window.rom_studio.dashboard_handoff_eyebrow.text().startswith(
            "GUARDIAN CORE HANDOFF"
        )
        assert manifest.manifest_digest[:16] in window.rom_studio.dashboard_handoff_detail.text()
        assert "Execution authority: NONE" in window.rom_studio.dashboard_handoff_detail.text()

        window.rom_studio.set_devices([])
        window._navigate_route("guardian_core")
        app.processEvents()
        assert window.guardian_center.studio_review_identity is None
        assert window.guardian_center.studio_review_badge.text() == "CONTEXT REFUSED"
        assert "No action started" in window.guardian_center.studio_review_detail.text()
    finally:
        window.companion_center.transport.close()
        window.close()


def test_ready_nexus_plan_opens_exact_zero_authority_guardian_context(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    store, registry, project, _report = _project(tmp_path)
    window = MainWindow(None, logo, store.workspace, app_icon_path=logo, pack_registry=registry)
    try:
        window.rom_studio.set_devices([_device()])
        app.processEvents()
        profile = window.rom_studio.device_dna.profiles.load(project.project_id)
        matrix = window.rom_studio.compatibility.matrices.load(project.project_id)
        assert profile is not None
        assert matrix is not None
        plan = NexusPlanner(store).plan(profile, matrix, NexusObjective.BUILD_ROM)
        assert plan.ready_for_guardian_review
        window.nexus_center.refresh()
        assert window.nexus_center.current_plan == plan
        window._navigate_route("nexus")
        window.nexus_center.guardian_button.click()
        app.processEvents()

        assert window.stack.currentWidget() is window.guardian_center
        assert not window.guardian_center.nexus_review.isHidden()
        assert plan.plan_digest[:16] in window.guardian_center.nexus_review_detail.text()
        assert "Device DNA" in window.guardian_center.nexus_review_title.text()
        assert window.guardian_center.nexus_review_badge.text() == "ZERO AUTHORITY"
        assert window.guardian_center.worker is None

        window.guardian_center.nexus_return_button.click()
        app.processEvents()
        assert window.stack.currentWidget() is window.nexus_center
        assert window.nexus_center.current_plan == plan

        window.nexus_center.open_studio_button.click()
        app.processEvents()
        assert window.stack.currentWidget() is window.rom_studio
        assert window.rom_studio.current_project is not None
        assert window.rom_studio.current_project.project_id == project.project_id
        assert plan.plan_digest[:16] in window.rom_studio.dashboard_handoff_detail.text()
        assert "objective build rom" in window.rom_studio.dashboard_handoff_detail.text()
        assert "NO PROJECT WORKER, PLAN, BUILD, OR PHONE ACTION STARTED" in (
            window.rom_studio.dashboard_handoff_detail.text()
        )
        assert window.rom_studio.worker is None
    finally:
        window.companion_center.transport.close()
        window.close()


def test_nexus_guardian_route_rejects_mismatched_plan_identity_in_page(
    tmp_path: Path,
) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    store, registry, project, _report = _project(tmp_path)
    window = MainWindow(None, logo, store.workspace, app_icon_path=logo, pack_registry=registry)
    try:
        profile = window.rom_studio.device_dna.profiles.load(project.project_id)
        matrix = window.rom_studio.compatibility.matrices.load(project.project_id)
        assert profile is not None
        assert matrix is not None
        plan = NexusPlanner(store).plan(profile, matrix, NexusObjective.BUILD_ROM)
        window.nexus_center.refresh()
        window._navigate_route("nexus")
        window.nexus_center.guardian_requested.emit(plan.project_id, "0" * 64)
        app.processEvents()

        assert window.stack.currentWidget() is window.nexus_center
        assert window.guardian_center.nexus_review.isHidden()
        assert "GUARDIAN HANDOFF STOPPED" in window.nexus_center.status.text()
        assert "no approval or execution" in window.nexus_center.status.text().casefold()
        assert window.guardian_center.worker is None
    finally:
        window.companion_center.transport.close()
        window.close()


def test_nexus_rom_studio_route_refuses_a_superseded_displayed_plan(
    tmp_path: Path,
) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    store, registry, project, _report = _project(tmp_path)
    window = MainWindow(None, logo, store.workspace, app_icon_path=logo, pack_registry=registry)
    try:
        window.rom_studio.set_devices([_device()])
        app.processEvents()
        profile = window.rom_studio.device_dna.profiles.load(project.project_id)
        matrix = window.rom_studio.compatibility.matrices.load(project.project_id)
        assert profile is not None and matrix is not None
        displayed = NexusPlanner(store).plan(profile, matrix, NexusObjective.BUILD_ROM)
        window.nexus_center.refresh()
        window._navigate_route("nexus")
        assert window.nexus_center.current_plan == displayed

        replacement = NexusPlanner(store).plan(profile, matrix, NexusObjective.ROOT_ROM)
        assert replacement.plan_digest != displayed.plan_digest
        window.nexus_center.open_studio_button.click()
        app.processEvents()

        assert window.stack.currentWidget() is window.nexus_center
        assert "ROM STUDIO HANDOFF STOPPED" in window.nexus_center.status.text()
        assert "project or plan no longer matches" in window.nexus_center.status.text()
        assert "No project worker, plan, build, or phone action started" in (
            window.nexus_center.status.text()
        )
        assert window.rom_studio.worker is None
    finally:
        window.companion_center.transport.close()
        window.close()


def test_guardian_expires_retained_nexus_context_when_plan_changes(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    store, registry, project, _report = _project(tmp_path)
    window = MainWindow(None, logo, store.workspace, app_icon_path=logo, pack_registry=registry)
    try:
        window.rom_studio.set_devices([_device()])
        app.processEvents()
        profile = window.rom_studio.device_dna.profiles.load(project.project_id)
        matrix = window.rom_studio.compatibility.matrices.load(project.project_id)
        assert profile is not None
        assert matrix is not None
        plan = NexusPlanner(store).plan(profile, matrix, NexusObjective.BUILD_ROM)
        window.nexus_center.refresh()
        window.nexus_center.guardian_button.click()
        app.processEvents()
        assert window.guardian_center.nexus_review_identity == (
            plan.project_id,
            plan.plan_digest,
        )

        NexusPlanner(store).plan(profile, matrix, NexusObjective.ROOT_ROM)
        window.guardian_center.nexus_return_button.click()
        app.processEvents()

        assert window.stack.currentWidget() is window.guardian_center
        assert window.guardian_center.nexus_review_identity is None
        assert window.guardian_center.nexus_review_badge.text() == "CONTEXT REFUSED"
        assert "no longer matches" in window.guardian_center.nexus_review_detail.text()
        assert "No action started" in window.guardian_center.nexus_review_detail.text()
        assert window.guardian_center.worker is None
    finally:
        window.companion_center.transport.close()
        window.close()


def test_time_machine_opens_exact_guardian_context_and_expires_superseded_plan(
    tmp_path: Path,
) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(None, logo, tmp_path, app_icon_path=logo)
    device = AndroidDevice(
        "private-backup-device",
        DeviceState.DEVICE,
        manufacturer="RadForge",
        model="Reference Phone",
        battery_percent=84,
        storage=StorageInfo(percent_used=37),
        bootloader_locked=True,
        verified_boot="green",
    )
    try:
        window.backup_center.set_devices([device])
        with patch("romverse.ui.backup_center.QMessageBox.information"):
            window.backup_center.plan_button.click()
        loaded = window.backup_center.plan_store.load_latest()
        assert loaded.data is not None

        window.backup_center.guardian_button.click()
        app.processEvents()

        assert window.stack.currentWidget() is window.guardian_center
        assert not window.guardian_center.backup_review.isHidden()
        assert window.guardian_center.nexus_review.isHidden()
        assert window.guardian_center.backup_review_identity == (
            loaded.data["plan_id"],
            loaded.data["plan_digest"],
        )
        assert window.guardian_center.backup_review_badge.text() == "ZERO AUTHORITY"
        assert "Reference Phone" in window.guardian_center.backup_review_title.text()
        assert window.guardian_center.worker is None

        window.guardian_center.backup_return_button.click()
        app.processEvents()
        assert window.stack.currentWidget() is window.backup_center
        assert window.backup_center._selected_plan_id == loaded.data["plan_id"]

        replacement = window.backup_center.plan_store.create(device)
        window._open_backup_guardian_review(
            replacement.plan_id,
            replacement.plan_digest,
        )
        window.backup_center.plan_store.create(device)
        window.guardian_center.backup_return_button.click()
        app.processEvents()

        assert window.stack.currentWidget() is window.guardian_center
        assert window.guardian_center.backup_review_identity is None
        assert window.guardian_center.backup_review_badge.text() == "CONTEXT REFUSED"
        assert "no longer matches" in window.guardian_center.backup_review_detail.text()
        assert "No action started" in window.guardian_center.backup_review_detail.text()
        assert window.guardian_center.worker is None
    finally:
        window.companion_center.transport.close()
        window.close()


def test_command_deck_repair_uses_exact_current_diagnostic_plan(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(
        None,
        logo,
        tmp_path,
        app_icon_path=logo,
        app_settings=AppSettings(online_intelligence_enabled=False),
    )
    snapshot = AndroidDevice(
        "private-command-device",
        DeviceState.DEVICE,
        manufacturer="RadForge",
        model="Reference Phone",
        battery_percent=75,
        storage=StorageInfo(percent_used=98),
        security_patch="2026-07-01",
        bootloader_locked=True,
        verified_boot="green",
        root_detected=False,
    )
    try:
        window.device_center.set_devices([snapshot])
        window.repair_center.set_devices([snapshot])
        window.diagnostics_center.set_devices([snapshot])
        app.processEvents()
        repair = window.device_center.quick_action_buttons["Repair Phone"]
        assert "STORAGE PLAN READY" in repair.text()
        assert repair.property("diagnosticFinding") == "storage.capacity"
        assert repair.property("evidenceReady") is True

        repair.click()
        app.processEvents()

        assert window.stack.currentWidget() is window.repair_center
        assert window.repair_center.current_concern is RepairConcern.STORAGE
        assert "STORAGE.CAPACITY" in window.repair_center.diagnostic_context.text()
        assert not window.repair_center.diagnostic_source_button.isHidden()
        assert window.repair_center.active_session is None
        assert window.repair_center.host_repair_worker is None
        assert window.repair_center.online_worker is None
    finally:
        window.companion_center.transport.close()
        window.close()


def test_command_deck_repair_uses_honest_general_intake_without_warning(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(None, logo, tmp_path, app_icon_path=logo)
    snapshot = AndroidDevice(
        "private-healthy-device",
        DeviceState.DEVICE,
        battery_percent=75,
        storage=StorageInfo(percent_used=45),
        security_patch="2026-07-01",
        bootloader_locked=True,
        verified_boot="green",
        root_detected=False,
    )
    try:
        window.device_center.set_devices([snapshot])
        window.repair_center.set_devices([snapshot])
        window.diagnostics_center.set_devices([snapshot])
        app.processEvents()
        repair = window.device_center.quick_action_buttons["Repair Phone"]
        assert "DEVICE READY" in repair.text()

        repair.click()
        app.processEvents()

        assert window.stack.currentWidget() is window.repair_center
        assert "NO CURRENT ACTIONABLE DIAGNOSTIC" in (
            window.repair_center.diagnostic_context.text()
        )
        assert window.repair_center.diagnostic_source_button.isHidden()
        assert window.repair_center.active_session is None
        assert window.repair_center.host_repair_worker is None
    finally:
        window.companion_center.transport.close()
        window.close()


def test_command_deck_repair_refuses_mismatched_recovery_evidence(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(None, logo, tmp_path, app_icon_path=logo)
    warning = AndroidDevice(
        "private-command-device",
        DeviceState.DEVICE,
        battery_percent=75,
        storage=StorageInfo(percent_used=98),
        security_patch="2026-07-01",
        bootloader_locked=True,
        verified_boot="green",
        root_detected=False,
    )
    healthy = AndroidDevice(
        "private-command-device",
        DeviceState.DEVICE,
        battery_percent=75,
        storage=StorageInfo(percent_used=45),
        security_patch="2026-07-01",
        bootloader_locked=True,
        verified_boot="green",
        root_detected=False,
    )
    try:
        window.device_center.set_devices([warning])
        window.repair_center.set_devices([healthy])
        window.diagnostics_center.set_devices([warning])
        app.processEvents()

        window.device_center.quick_action_buttons["Repair Phone"].click()
        app.processEvents()

        assert window.stack.currentWidget() is window.repair_center
        assert "EXACT DIAGNOSTIC NEEDS FRESH EVIDENCE" in (
            window.repair_center.diagnostic_context.text()
        )
        assert window.repair_center.diagnostic_source_button.isHidden()
        assert window.repair_center.active_session is None
        assert window.repair_center.host_repair_worker is None
    finally:
        window.companion_center.transport.close()
        window.close()


def test_command_deck_recovery_rejects_same_finding_from_a_different_device(
    tmp_path: Path,
) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    store, registry, project, _report = _project(tmp_path)
    window = MainWindow(
        None,
        logo,
        store.workspace,
        app_icon_path=logo,
        pack_registry=registry,
        app_settings=AppSettings(online_intelligence_enabled=False),
    )
    phone_a = _device(
        serial="DIAGNOSTIC-PHONE-A",
        storage=StorageInfo(percent_used=98),
    )
    phone_b = _device(
        serial="SELECTED-PHONE-B",
        storage=StorageInfo(percent_used=98),
    )
    try:
        window.rom_studio.refresh(project.project_id)
        window._observed_devices = [phone_b]
        window._selected_device_serial = phone_b.serial
        window.device_center.set_devices([phone_b], phone_b.serial)
        window.repair_center.set_devices([phone_b])
        window.diagnostics_center.set_devices([phone_a])
        app.processEvents()
        assert window.diagnostics_center.current_device == phone_a
        assert window.repair_center.current_device == phone_b
        assert window.device_center.primary_action_buttons["Recover Device"].isEnabled()
        before_incidents = window.repair_center.autopilot_service.list_recent()

        window.device_center.primary_action_buttons["Recover Device"].click()
        app.processEvents()

        assert window.stack.currentWidget() is window.repair_center
        assert "EXACT DIAGNOSTIC NEEDS FRESH EVIDENCE" in (
            window.repair_center.diagnostic_context.text()
        )
        assert window.repair_center.diagnostic_source_button.isHidden()
        assert window.repair_center.current_device == phone_b
        assert window.rom_studio.current_project is not None
        assert window.rom_studio.current_project.project_id == project.project_id
        assert window.repair_center.autopilot_service.list_recent() == before_incidents
        assert window.repair_center.autopilot_incident is None
        assert window.repair_center.active_session is None
        assert window.repair_center.host_repair_worker is None
        assert window.repair_center.online_worker is None
    finally:
        window.companion_center.transport.close()
        window.close()


def test_command_deck_resume_opens_only_the_current_project_mission(
    tmp_path: Path,
) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    store, registry, project, _report = _project(tmp_path)
    unrelated = store.create("Unrelated retained project")
    window = MainWindow(
        None,
        logo,
        store.workspace,
        app_icon_path=logo,
        pack_registry=registry,
        app_settings=AppSettings(online_intelligence_enabled=False),
    )
    phone = _device(serial="CURRENT-MISSION-PHONE")
    current = window.nexus_events.start(
        source="ROM Studio",
        stage="inspect",
        title="Current project inspection",
        summary="The current project's real inspection is running.",
        explanation="The producing service recorded this exact current mission.",
        next_action="Keep ROMVERSE open.",
        project_id=project.project_id,
    )
    unrelated_newer = window.nexus_events.start(
        source="ROM Studio",
        stage="build",
        title="Unrelated project build",
        summary="Another project's retained event is newer.",
        explanation="This event must not become the current project's mission.",
        next_action="Review the unrelated project separately.",
        project_id=unrelated.project_id,
    )
    try:
        window.rom_studio.refresh(project.project_id)
        window._observed_devices = [phone]
        window._selected_device_serial = phone.serial
        window.device_center.set_devices([phone], phone.serial)
        window._sync_command_deck_context()
        app.processEvents()
        before = window.nexus_events.list_recent()

        assert window.device_center._next_action_key == "Live Operations"
        assert window.device_center.next_title.text() == current.title
        assert unrelated_newer.title not in window.device_center.next_title.text()

        window.device_center.primary_action_buttons["Resume Mission"].click()
        app.processEvents()

        assert window.stack.currentWidget() is window.live_console
        assert window.live_console.table.rowCount() == 1
        assert window.live_console.detail_title.text() == current.title
        assert "EXACT MISSION LEDGER" in window.live_console.status.text()
        assert window.rom_studio.current_project is not None
        assert window.rom_studio.current_project.project_id == project.project_id
        assert window.device_center.selected_device() == phone
        assert window.nexus_events.list_recent() == before
        assert (
            next(item for item in before if item.mission_id == current.mission_id).state
            is MissionState.RUNNING
        )
        assert (
            next(item for item in before if item.mission_id == unrelated_newer.mission_id).state
            is MissionState.RUNNING
        )
        assert window.rom_studio.worker is None
        assert window.repair_center.host_repair_worker is None
        assert window.repair_center.online_worker is None
        assert not QApplication.activeModalWidget()
    finally:
        window.companion_center.transport.close()
        window.close()


def test_command_deck_stale_live_resume_falls_back_to_current_genesis(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    store, registry, project, _report = _project(tmp_path)
    unrelated = store.create("Unrelated active project")
    window = MainWindow(
        None,
        logo,
        store.workspace,
        app_icon_path=logo,
        pack_registry=registry,
        app_settings=AppSettings(online_intelligence_enabled=False),
    )
    current = window.nexus_events.start(
        source="ROM Studio",
        stage="inspect",
        title="Current project inspection",
        summary="The current project's operation was running.",
        explanation="The producer owns this state.",
        next_action="Wait for a durable outcome.",
        project_id=project.project_id,
    )
    window.nexus_events.start(
        source="ROM Studio",
        stage="build",
        title="Other project still running",
        summary="This retained mission belongs to another project.",
        explanation="It grants no ownership over the selected project.",
        next_action="Review it from its own project.",
        project_id=unrelated.project_id,
    )
    try:
        window.rom_studio.refresh(project.project_id)
        window._sync_command_deck_context()
        assert window.device_center._next_action_key == "Live Operations"
        genesis_opened: list[bool] = []
        monkeypatch.setattr(
            window.rom_studio,
            "_open_guided_setup",
            lambda: genesis_opened.append(True),
        )

        window.nexus_events.finish(
            current.mission_id,
            MissionState.SUCCEEDED,
            summary="The current operation completed.",
            explanation="The producing service reported its durable result.",
            next_action="Continue the existing Genesis journey.",
            confidence=MissionConfidence.VERIFIED,
        )
        before = window.nexus_events.list_recent()

        window.device_center.primary_action_buttons["Resume Mission"].click()
        app.processEvents()

        assert window.stack.currentWidget() is window.rom_studio
        assert window.rom_studio.current_project is not None
        assert window.rom_studio.current_project.project_id == project.project_id
        assert genesis_opened == [True]
        assert window.nexus_events.list_recent() == before
        assert window.live_console._mission_context_id == ""
        assert window.rom_studio.worker is None
        assert not QApplication.activeModalWidget()
    finally:
        window.companion_center.transport.close()
        window.close()


def test_mission_pulse_direct_live_operations_restores_the_global_ledger(
    tmp_path: Path,
) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    store, registry, project, _report = _project(tmp_path)
    unrelated = store.create("Global ledger project")
    window = MainWindow(
        None,
        logo,
        store.workspace,
        app_icon_path=logo,
        pack_registry=registry,
        app_settings=AppSettings(online_intelligence_enabled=False),
    )
    current = window.nexus_events.start(
        source="ROM Studio",
        stage="inspect",
        title="Scoped current mission",
        summary="This project mission is active.",
        explanation="Resume should initially scope to this mission.",
        next_action="Review its exact ledger.",
        project_id=project.project_id,
    )
    unrelated_event = window.nexus_events.note(
        source="ROMVERSE Nexus",
        stage="planning",
        title="Unrelated global event",
        summary="This genuine event belongs in deliberate global navigation.",
        explanation="It must remain outside the scoped Resume view.",
        next_action="Review it from the global ledger.",
        project_id=unrelated.project_id,
    )
    try:
        window.rom_studio.refresh(project.project_id)
        window._sync_command_deck_context()
        window.show()
        app.processEvents()

        window.device_center.primary_action_buttons["Resume Mission"].click()
        app.processEvents()
        assert window.live_console.table.rowCount() == 1
        assert window.live_console.detail_title.text() == current.title

        window._navigate_route("command_deck")
        app.processEvents()
        pulse = window.device_center.findChild(QFrame, "CommandDeckMissionPulse")
        open_global = next(
            button
            for button in pulse.findChildren(QPushButton)
            if button.text() == "Open Live Operations"
        )
        before = window.nexus_events.list_recent()
        open_global.click()
        app.processEvents()

        visible_ids = {
            window.live_console.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            for row in range(window.live_console.table.rowCount())
        }
        assert window.stack.currentWidget() is window.live_console
        assert "EXACT MISSION LEDGER" not in window.live_console.status.text()
        assert current.event_id in visible_ids
        assert unrelated_event.event_id in visible_ids
        assert window.nexus_events.list_recent() == before
        assert window.rom_studio.worker is None
        assert window.repair_center.host_repair_worker is None
        assert window.repair_center.online_worker is None
    finally:
        window.companion_center.transport.close()
        window.close()


def test_expert_mode_is_applied_from_persisted_settings_without_changing_guardian(
    tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(
        None,
        logo,
        tmp_path,
        app_icon_path=logo,
        app_settings=AppSettings(experience_mode=ExperienceMode.EXPERT),
    )
    try:
        by_label = {button.text().replace("&&", "&"): button for button in window.nav_buttons}
        assert not by_label["Command Console"].isHidden()
        assert not by_label["ROMVERSE Nexus"].isHidden()
        assert not by_label["Forge Arsenal"].isHidden()
        assert not by_label["Guardian Core"].isHidden()
        assert "Guardian" in window.experience_badge.toolTip()
    finally:
        window.companion_center.transport.close()
        window.close()


def test_desktop_theme_is_applied_at_startup_and_new_choice_is_persistable(
    tmp_path: Path,
) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(
        None,
        logo,
        tmp_path,
        app_icon_path=logo,
        app_settings=AppSettings(desktop_theme=DesktopTheme.SOLAR_FLARE),
    )
    saved: list[AppSettings] = []
    window.settings_changed.connect(saved.append)
    try:
        assert window.app_settings.desktop_theme is DesktopTheme.SOLAR_FLARE
        assert window.device_center.export_button.text() == "Theme · Solar Flare  ⌄"
        assert "border-color:#806137" in app.styleSheet()

        window._apply_theme(DesktopTheme.QUANTUM_MINT)
        app.processEvents()

        assert window.app_settings.desktop_theme is DesktopTheme.QUANTUM_MINT
        assert window.rom_studio.app_settings.desktop_theme is DesktopTheme.QUANTUM_MINT
        assert saved == [window.app_settings]
        assert saved[0].schema_version == 5
        assert window.device_center.export_button.text() == "Theme · Quantum Mint  ⌄"
        assert "border-color:#2E776D" in app.styleSheet()
        assert "applied and saved" in window.device_center.device_note.text()
        assert window.guardian_center.worker is None
        assert window.rom_studio.worker is None
    finally:
        window.companion_center.transport.close()
        window.close()
        app.setStyleSheet(STYLESHEET)


def test_online_setting_immediately_controls_the_global_reachability_monitor(
    tmp_path: Path,
) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(
        None,
        logo,
        tmp_path,
        app_icon_path=logo,
        app_settings=AppSettings(online_intelligence_enabled=False),
    )
    saved: list[AppSettings] = []
    window.settings_changed.connect(saved.append)
    try:
        assert window.online_status.label.text() == "LOCAL"
        assert not window.online_status.monitoring_enabled
        with patch("romverse.ui.main_window.SettingsDialog") as dialog_type:
            dialog = dialog_type.return_value
            dialog.exec.return_value = QDialog.DialogCode.Accepted
            dialog.values.return_value = replace(
                window.app_settings,
                online_intelligence_enabled=True,
            )
            window._open_settings()

            assert window.online_status.monitoring_enabled
            assert window.online_status.label.text() == "CHECKING"
            assert window.online_status.timer.isActive()

            dialog.values.return_value = replace(
                window.app_settings,
                online_intelligence_enabled=False,
            )
            window._open_settings()

        app.processEvents()
        assert not window.online_status.monitoring_enabled
        assert window.online_status.label.text() == "LOCAL"
        assert window.online_status.reply is None
        assert not window.online_status.timer.isActive()
        assert [item.online_intelligence_enabled for item in saved] == [True, False]
        assert window.device_catalog_worker is None
        assert window.active_worker is None
        assert window.rom_studio.worker is None
        assert window.guardian_center.worker is None
    finally:
        window.companion_center.transport.close()
        window.close()


def test_genesis_learning_route_opens_archives_with_the_exact_guide(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(None, logo, tmp_path, app_icon_path=logo)
    try:
        window.rom_studio.knowledge_requested.emit("firmware source")
        app.processEvents()

        assert window.stack.currentIndex() == window.knowledge_index
        assert window.knowledge_center.search.text() == "firmware source"
        assert "payload.bin" in window.knowledge_center.detail.toPlainText().casefold()
        active = [item for item in window.nav_buttons if item.property("active")]
        assert len(active) == 1
        assert active[0].text().replace("&&", "&") == "ROMVERSE Archives"
    finally:
        window.companion_center.transport.close()
        window.close()


def test_typed_advisor_handoff_opens_the_exact_archives_identity(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(None, logo, tmp_path, app_icon_path=logo)
    try:
        window.diagnostics_center.knowledge_article_requested.emit("device-battery-low")
        app.processEvents()

        assert window.stack.currentWidget() is window.knowledge_center
        assert window.knowledge_center.list.count() == 1
        assert window.knowledge_center.search.text() == (
            "Device battery is below the safe maintenance threshold"
        )
        assert "CHARGING IS USER CONTROLLED" in window.knowledge_center.detail.toPlainText()
        active = [item for item in window.nav_buttons if item.property("active")]
        assert len(active) == 1
        assert active[0].text().replace("&&", "&") == "ROMVERSE Archives"
    finally:
        window.companion_center.transport.close()
        window.close()


def test_nexus_missing_evidence_opens_exact_guide_then_rom_studio(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(None, logo, tmp_path, app_icon_path=logo)
    try:
        assert window.nexus_center.current_plan is None
        assert not window.nexus_center.generate_button.isEnabled()
        window.nexus_center.evidence_guide_button.click()
        app.processEvents()

        assert window.stack.currentWidget() is window.knowledge_center
        assert window.knowledge_center.list.count() == 1
        assert window.knowledge_center.search.text() == (
            "Nexus cannot generate a plan because project evidence is missing"
        )
        assert window.knowledge_center.open_route.property("route") == "rom_studio"
        assert "NO PLAN, APPROVAL, OR EXECUTION" in (window.knowledge_center.detail.toPlainText())
        window.knowledge_center.open_route.click()
        app.processEvents()

        assert window.stack.currentWidget() is window.rom_studio
        assert window.nexus_center.current_plan is None
    finally:
        window.companion_center.transport.close()
        window.close()


def test_apk_failure_opens_exact_guide_and_returns_to_unchanged_launchpad(
    tmp_path: Path,
) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(None, logo, tmp_path, app_icon_path=logo)
    try:
        window._navigate_route("app_launchpad")
        window.apk_installer.set_devices([_apk_device()])
        plan = _apk_ready_plan(tmp_path)
        window.apk_installer._plan_ready(plan)
        with patch("romverse.ui.apk_center.QMessageBox.warning"):
            window.apk_installer._install_complete(
                CommandResult(
                    ("adb",),
                    1,
                    "",
                    "Failure [INSTALL_FAILED_VERSION_DOWNGRADE: older version]",
                )
            )
        window.apk_installer.failure_guide_button.click()
        app.processEvents()

        assert window.stack.currentWidget() is window.knowledge_center
        assert window.knowledge_center.list.count() == 1
        assert window.knowledge_center.search.text() == (
            "APK install error: INSTALL_FAILED_VERSION_DOWNGRADE"
        )
        assert window.knowledge_center.source_return.text() == "Return to App Launchpad"
        assert window.apk_installer.current_plan is plan
        assert window.apk_installer.active_worker is None

        window.knowledge_center.source_return.click()
        app.processEvents()

        assert window.stack.currentWidget() is window.apk_installer
        assert window.apk_installer.current_plan is plan
        assert not window.apk_installer.failure_guidance.isHidden()
        assert window.apk_installer.active_worker is None
    finally:
        window.companion_center.transport.close()
        window.close()


def test_optimizer_exact_finding_opens_matching_recovery_plan(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(
        None,
        logo,
        tmp_path,
        app_icon_path=logo,
        app_settings=AppSettings(online_intelligence_enabled=False),
    )
    snapshot = AndroidDevice(
        "private-storage-device",
        DeviceState.DEVICE,
        manufacturer="RadForge",
        model="Reference Phone",
        battery_percent=75,
        battery_temperature_c=31.0,
        storage=StorageInfo(percent_used=98),
        security_patch="2026-07-01",
        bootloader_locked=True,
        verified_boot="green",
        root_detected=False,
        connection_note="Connected",
    )
    try:
        window.diagnostics_center.set_devices([snapshot])
        window.repair_center.set_devices([snapshot])
        window._navigate_route("quantum_optimizer")
        app.processEvents()
        button = next(
            item
            for item in window.diagnostics_center.findChildren(QPushButton)
            if item.text() == "Open guided fix in Recovery Bay"
        )

        button.click()
        app.processEvents()

        assert window.stack.currentWidget() is window.repair_center
        assert window.repair_center.current_concern is RepairConcern.STORAGE
        assert "STORAGE.CAPACITY" in window.repair_center.diagnostic_context.text()
        assert "NO ACTION STARTED" in window.repair_center.diagnostic_context.text()
        assert window.repair_center.active_session is None
        assert window.repair_center.host_repair_worker is None
        assert window.repair_center.online_worker is None

        window.repair_center.diagnostic_source_button.click()
        app.processEvents()

        assert window.stack.currentWidget() is window.diagnostics_center
        source_card = window.diagnostics_center.finding_cards["storage.capacity"]
        assert source_card.property("diagnosticFocus") is True
        assert not source_card.source_context.isHidden()
        assert "Recovery Bay source" in window.diagnostics_center.saved_label.text()
        assert window.repair_center.active_session is None
        assert window.repair_center.host_repair_worker is None
    finally:
        window.companion_center.transport.close()
        window.close()


def test_optimizer_recovery_handoff_fails_closed_on_stale_evidence(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(None, logo, tmp_path, app_icon_path=logo)
    try:
        window._navigate_route("quantum_optimizer")
        previous_page = window.stack.currentWidget()

        window.diagnostics_center.repair_requested.emit("storage.capacity")
        app.processEvents()

        assert window.stack.currentWidget() is previous_page
        assert window.notification_center.last_notification is not None
        assert window.notification_center.last_notification.key == (
            "repair.handoff.storage.capacity"
        )
        assert "fresh evidence" in window.notification_center.last_notification.title.casefold()
        assert "Recovery handoff stopped" in window.diagnostics_center.saved_label.text()
        assert "nothing started" in window.diagnostics_center.saved_label.text()
        assert window.repair_center.active_session is None
        assert window.repair_center.host_repair_worker is None
    finally:
        window.companion_center.transport.close()
        window.close()


def test_recovery_source_handoff_fails_closed_when_finding_is_stale(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(None, logo, tmp_path, app_icon_path=logo)
    try:
        window._navigate_route("recovery_bay")
        previous_page = window.stack.currentWidget()

        window.repair_center.diagnostic_requested.emit("storage.capacity")
        app.processEvents()

        assert window.stack.currentWidget() is previous_page
        assert window.notification_center.last_notification is not None
        assert window.notification_center.last_notification.key == (
            "diagnostics.handoff.storage.capacity"
        )
        assert "fresh evidence" in window.notification_center.last_notification.title.casefold()
        assert "SOURCE RETURN STOPPED" in window.repair_center.diagnostic_context.text()
        assert "NO ACTION STARTED" in window.repair_center.diagnostic_context.text()
        assert window.repair_center.active_session is None
        assert window.repair_center.host_repair_worker is None
    finally:
        window.companion_center.transport.close()
        window.close()


def test_handoff_failures_remain_visible_when_desktop_notifications_are_disabled(
    tmp_path: Path,
) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(
        None,
        logo,
        tmp_path,
        app_icon_path=logo,
        app_settings=AppSettings(desktop_notifications_enabled=False),
    )
    try:
        window._navigate_route("quantum_optimizer")
        window.diagnostics_center.repair_requested.emit("storage.capacity")
        app.processEvents()

        assert window.stack.currentWidget() is window.diagnostics_center
        assert window.notification_center.last_notification is None
        assert "storage.capacity needs fresh evidence" in (
            window.diagnostics_center.saved_label.text()
        )
        assert "nothing started" in window.diagnostics_center.saved_label.text()

        window._navigate_route("recovery_bay")
        window.repair_center.diagnostic_requested.emit("storage.capacity")
        app.processEvents()

        assert window.stack.currentWidget() is window.repair_center
        assert window.notification_center.last_notification is None
        assert "SOURCE RETURN STOPPED" in window.repair_center.diagnostic_context.text()
        assert "REFRESH DEVICE EVIDENCE" in window.repair_center.diagnostic_context.text()
        assert window.repair_center.active_session is None
        assert window.repair_center.host_repair_worker is None
    finally:
        window.companion_center.transport.close()
        window.close()


def test_fresh_repair_comparison_refreshes_exact_local_archives_memory(
    tmp_path: Path,
) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(
        None,
        logo,
        tmp_path,
        app_icon_path=logo,
        app_settings=AppSettings(online_intelligence_enabled=False),
    )
    initial = AndroidDevice(
        "private-learning-device",
        DeviceState.DEVICE,
        manufacturer="RadForge",
        model="Reference Phone",
        battery_percent=8,
        battery_temperature_c=31.0,
        connection_note="Connected",
    )
    improved = AndroidDevice(
        "private-learning-device",
        DeviceState.DEVICE,
        manufacturer="RadForge",
        model="Reference Phone",
        battery_percent=70,
        battery_temperature_c=31.0,
        connection_note="Connected",
    )
    try:
        window.repair_center.set_devices([initial])
        window.repair_center._start_session()
        assert window.repair_center.active_session is not None
        window.repair_center._pending_verification_session = (
            window.repair_center.active_session.session_id
        )

        window.repair_center.set_devices([improved])
        app.processEvents()

        assert window.repair_center.active_session is not None
        assert window.repair_center.active_session.verification_direction == "improved"
        window.repair_center.knowledge_article_requested.emit("device-battery-low")
        app.processEvents()

        assert window.stack.currentWidget() is window.knowledge_center
        assert window.knowledge_center.resolution_status.isVisibleTo(window.knowledge_center)
        assert "1 IMPROVED" in window.knowledge_center.resolution_status.text()
        assert "INTERPRETATION BOUNDARY" in window.knowledge_center.detail.toPlainText()
        assert "does not prove" in window.knowledge_center.detail.toPlainText()
        assert "private-learning-device" not in window.knowledge_center.detail.toPlainText()
    finally:
        window.companion_center.transport.close()
        window.close()


def test_recovery_bay_archives_handoff_and_canonical_fix_route_are_connected(
    tmp_path: Path,
) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(None, logo, tmp_path, app_icon_path=logo)
    try:
        window.repair_center.symptom_input.setText("adb unauthorized")
        window.repair_center.archives_button.click()
        app.processEvents()

        assert window.stack.currentWidget() is window.knowledge_center
        assert window.knowledge_center.search.text() == "adb unauthorized"
        assert window.knowledge_center.open_route.property("route") == "command_deck"
        window.knowledge_center.open_route.click()
        app.processEvents()
        assert window.stack.currentWidget() is window.device_center
    finally:
        window.companion_center.transport.close()
        window.close()


def test_failed_device_refresh_clears_stale_rom_studio_identity(tmp_path: Path) -> None:
    QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(None, logo, tmp_path, app_icon_path=logo)
    finished = []
    window.rom_studio.device_scan_finished.connect(
        lambda succeeded, message: finished.append((succeeded, message))
    )
    window.rom_studio.set_devices(
        [AndroidDevice("stale-serial", DeviceState.DEVICE, model="Stale phone")]
    )
    window.device_center.set_repair_context("storage.capacity", "Device storage is nearly full")

    try:
        window._scan_failed("ADB transport failed during refresh")

        assert window.device_center.devices == []
        assert window.diagnostics_center.devices == []
        assert window.repair_center.devices == []
        assert window.rom_studio.devices == []
        assert finished == [(False, "ADB transport failed during refresh")]
        assert window.connection_state.text() == "⌁  Reconnecting Device Engine"
        assert window.connection_state.objectName() == "Warning"
        assert window.sidebar_device_state.objectName() == "Warning"
        assert window._reconnect_timer.isActive()
        assert "automatic retry" in window.sidebar_device_detail.text()
        assert any(
            button.text() == "Resolve Platform Tools"
            for button in window.device_center.findChildren(QPushButton)
        )
    finally:
        window.companion_center.transport.close()
        window.close()


def test_failed_device_refresh_routes_exact_offline_diagnosis_to_archives(
    tmp_path: Path,
) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(
        None,
        logo,
        tmp_path,
        app_icon_path=logo,
        app_settings=AppSettings(online_intelligence_enabled=False),
    )
    error = "adb: error: more than one device/emulator"

    try:
        window._scan_failed(error)
        app.processEvents()

        report = window.repair_center.offline_report
        assert report is not None
        assert report.trigger == "device-discovery-failure"
        assert report.execution_authority == "none"
        assert report.matches[0].record.record_id == "catalog.adb-multiple-targets"
        assert window.repair_center.host_repair_worker is None

        review = next(
            button
            for button in window.repair_center.findChildren(QPushButton)
            if button.text() == "Review all matching offline evidence"
        )
        review.click()
        app.processEvents()

        assert window.stack.currentWidget() is window.knowledge_center
        assert window.knowledge_center.search.text() == error
        assert "ADB found multiple transports" in window.knowledge_center.detail.toPlainText()
        assert window.repair_center.host_repair_worker is None
    finally:
        window.companion_center.transport.close()
        window.close()


def test_fresh_scan_connects_exact_official_device_identity_to_every_desktop_consumer(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(GooglePlayDeviceCatalog, "MINIMUM_ENTRIES", 1)
    catalog = GooglePlayDeviceCatalog(tmp_path)
    _sync(
        catalog,
        _payload(("Example", "Example Nebula", "nebula", "EX-100")),
    )
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(
        None,
        logo,
        tmp_path,
        app_icon_path=logo,
        pack_registry=registry,
        app_settings=AppSettings(online_intelligence_enabled=False),
    )
    device = AndroidDevice(
        "private-catalog-device",
        DeviceState.DEVICE,
        brand="Example",
        manufacturer="Example Industries",
        model="EX-100",
        codename="nebula",
        android_version="16",
    )
    try:
        window._scan_complete([device])
        app.processEvents()

        assert window.device_center.devices[0].marketing_name == "Example Nebula"
        assert window.diagnostics_center.devices[0].marketing_name == "Example Nebula"
        assert window.rom_studio.devices[0].marketing_name == "Example Nebula"
        assert window.sidebar_device_name.text() == "Example Industries Example Nebula"
        assert window.connection_device.text() == (
            "Device: Example Industries Example Nebula (nebula)"
        )
        assert window.device_packs_center.identity_catalog_badge.text() == ("EXACT ID • READ ONLY")
        receipt = window.device_identity.load(window.device_center.devices[0])
        assert receipt is not None
        assert receipt.authority is IdentityAuthority.GOOGLE_PLAY_CATALOG
        assert window.device_catalog_worker is None
        assert window.device_center._knowledge_report is not None
        assert window.device_center._knowledge_report.trigger == "device-connection"
        assert window.device_center._knowledge_report.execution_authority == "none"
        assert any(
            event.title == "Offline device evidence lookup completed"
            for event in window.activity_store.list_recent(20)
        )

        readiness = next(
            event for event in window.nexus_events.list_recent() if event.source == "Device Atlas"
        )
        assert readiness.stage == "device-pack-readiness"
        assert "build is locked and flash is locked" in readiness.summary
        assert readiness.next_action == "Confirm the exact model contract"
        assert readiness.confidence is MissionConfidence.VERIFIED
        assert "identity=verified" in readiness.explanation
        assert "compile=locked" in readiness.explanation

        window._navigate_route("live_console")
        app.processEvents()
        readiness_row = next(
            row
            for row in range(window.live_console.table.rowCount())
            if window.live_console.table.item(row, 1).text() == "Device Atlas"
        )
        window.live_console.table.selectRow(readiness_row)
        app.processEvents()
        assert window.live_console.open_source_button.text() == "Open Device Atlas"
        window.live_console.open_source_button.click()
        assert window.stack.currentWidget() is window.device_packs_center

        action = window.device_packs_center.active_next_action
        report = window.device_packs_center.active_report
        assert action is not None and report is not None
        window._open_device_pack_next_action(
            action.route,
            action.article_key,
            action.check_id,
            "0" * 64,
        )
        assert window.stack.currentWidget() is window.device_packs_center
        assert "NEXT ACTION STOPPED" in window.device_packs_center.next_action_feedback.text()

        window.device_packs_center.next_action_button.click()
        app.processEvents()
        assert window.stack.currentWidget() is window.knowledge_center
        assert "Recognize an Android model" in window.knowledge_center.list.currentItem().text()
        window.knowledge_center.source_return.click()
        assert window.stack.currentWidget() is window.device_packs_center

        window._open_device_requirement(
            "compile",
            "archives",
            "device-build-requirements-blueprint",
            "0" * 64,
        )
        assert window.stack.currentWidget() is window.device_packs_center
        assert "COMPILE HANDOFF STOPPED" in (
            window.device_packs_center.requirements_feedback.text()
        )

        window.device_packs_center.requirement_buttons["compile"].click()
        app.processEvents()
        assert window.stack.currentWidget() is window.knowledge_center
        assert window.knowledge_center.list.currentItem().text() == (
            "Determine what a recognized Android device needs to build, compile, and flash"
        )
        assert window.knowledge_center.source_return.text() == "Return to Device Atlas"
    finally:
        window.companion_center.transport.close()
        window.close()


def test_fresh_scan_immediately_refreshes_the_command_deck_genesis_device_stage(
    tmp_path: Path,
) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    store, registry, project, _report = _project(tmp_path)
    store.create_working_copy(project.project_id)
    RomInspectionService(store).extract_project_tree(project.project_id)
    window = MainWindow(
        None,
        logo,
        store.workspace,
        app_icon_path=logo,
        pack_registry=registry,
        app_settings=AppSettings(online_intelligence_enabled=False),
    )
    try:
        window.rom_studio.refresh(project.project_id)
        window._sync_command_deck_context()
        assert window.device_center._flight_plan is not None
        assert any(
            "No Android device is currently visible" in blocker
            for blocker in window.device_center._flight_plan.blockers
        )

        window._scan_complete([_device()])
        app.processEvents()

        assert window.device_center._flight_plan == window.rom_studio.genesis_flight_plan()
        assert not any(
            "No Android device is currently visible" in blocker
            for blocker in window.device_center._flight_plan.blockers
        )

        window._scan_failed("ADB transport failed during refresh")
        app.processEvents()

        assert window.device_center._flight_plan == window.rom_studio.genesis_flight_plan()
        assert any(
            "latest USB device scan failed" in blocker
            for blocker in window.device_center._flight_plan.blockers
        )
        assert not any(
            "phone is disconnected" in blocker and "not treating" not in blocker
            for blocker in window.device_center._flight_plan.blockers
        )
    finally:
        window.companion_center.transport.close()
        window.close()


def test_desktop_preserves_detection_truth_without_granting_action_authority(
    tmp_path: Path,
) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    store, registry, project, _report = _project(tmp_path)
    store.create_working_copy(project.project_id)
    RomInspectionService(store).extract_project_tree(project.project_id)
    window = MainWindow(
        None,
        logo,
        store.workspace,
        app_icon_path=logo,
        pack_registry=registry,
        app_settings=AppSettings(online_intelligence_enabled=False),
    )
    try:
        window.rom_studio.refresh(project.project_id)

        unauthorized = AndroidDevice(
            "needs-approval",
            DeviceState.UNAUTHORIZED,
            manufacturer="Example",
            model="Visible Phone",
        )
        window._scan_complete([unauthorized])
        app.processEvents()

        assert window.rom_studio.devices == [unauthorized]
        assert window.rom_studio.observed_devices == [unauthorized]
        assert any(
            "USB phone detected" in blocker and "approve" in blocker
            for blocker in window.device_center._flight_plan.blockers
        )
        assert "authorization required" in window.companion_center.device_status.text()

        offline = AndroidDevice(
            "offline-phone",
            DeviceState.OFFLINE,
            manufacturer="Example",
            model="Visible Phone",
        )
        window._scan_complete([offline])
        app.processEvents()

        assert any(
            "ADB detected the phone, but it is offline" in blocker
            for blocker in window.device_center._flight_plan.blockers
        )
        assert "ADB offline" in window.companion_center.device_status.text()

        fastboot = AndroidDevice(
            "bootloader-phone",
            DeviceState.FASTBOOT,
            manufacturer="Example",
            model="Visible Phone",
        )
        window._scan_complete([fastboot])
        app.processEvents()

        assert any(
            "Phone detected in fastboot mode" in blocker
            for blocker in window.device_center._flight_plan.blockers
        )
        assert "fastboot mode" in window.companion_center.device_status.text()

        first = AndroidDevice("first", DeviceState.DEVICE, model="First Phone")
        second = AndroidDevice("second", DeviceState.DEVICE, model="Second Phone")
        window._scan_complete([first, second])
        app.processEvents()

        assert window.rom_studio.devices == []
        assert window.rom_studio.observed_devices == [first, second]
        assert any(
            "Choose one of the 2 detected Android devices" in blocker
            for blocker in window.device_center._flight_plan.blockers
        )
        assert "2 USB devices detected" in window.companion_center.device_status.text()
    finally:
        window.companion_center.transport.close()
        window.close()


def test_official_identity_missing_pack_opens_exact_archives_fix_and_returns_unchanged(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(GooglePlayDeviceCatalog, "MINIMUM_ENTRIES", 1)
    catalog = GooglePlayDeviceCatalog(tmp_path)
    _sync(catalog, _payload(("Example", "Example Nebula", "nebula", "EX-100")))
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(
        None,
        logo,
        tmp_path,
        app_icon_path=logo,
        pack_registry=registry,
        app_settings=AppSettings(online_intelligence_enabled=False),
    )
    try:
        assert not window.online_status.monitoring_enabled
        assert window.online_status.label.text() == "LOCAL"
        assert window.online_status.reply is None
        assert not window.online_status.timer.isActive()
        window._navigate_route("device_atlas")
        center = window.device_packs_center
        center.catalog_search.setText("Example Nebula")
        app.processEvents()
        center.official_result_buttons[0].click()
        app.processEvents()

        assert center.official_missing_pack_guide_button is not None
        center.official_missing_pack_guide_button.click()
        app.processEvents()

        assert window.stack.currentWidget() is window.knowledge_center
        assert window.knowledge_center.list.currentItem().text() == (
            "Official Android ID search finds a phone but no Device Pack"
        )
        assert window.knowledge_center.source_context.property("source_route") == ("device_atlas")
        assert window.knowledge_center.source_return.text() == "Return to Device Atlas"

        window.knowledge_center.source_return.click()
        app.processEvents()

        assert window.stack.currentWidget() is center
        labels = [label.text() for label in center.findChildren(QLabel)]
        assert "GOOGLE PLAY DEVICE ID  •  VERIFIED LOCAL MIRROR" in labels
        assert "No exact Device Pack is declared for this official identity" in labels
        assert center.active_device is None
        assert center.active_report is None
        assert window.active_worker is None
        assert window.device_catalog_worker is None
        assert window.rom_studio.worker is None
        assert window.guardian_center.worker is None
    finally:
        window.companion_center.transport.close()
        window.close()


def test_device_atlas_runs_official_id_sync_in_managed_worker_and_keeps_failure_visible(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    started = []
    monkeypatch.setattr("romverse.ui.main_window.start_background", started.append)
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(None, logo, tmp_path, app_icon_path=logo)
    status = DeviceCatalogStatus(
        True,
        True,
        "Official IDs current",
        53_575,
        "2026-09-01T00:00:00+00:00",
        "a" * 64,
    )
    content = _payload(("Example", "Example Nebula", "nebula", "EX-100"))
    update = DeviceCatalogUpdate(
        GOOGLE_PLAY_CATALOG_URL,
        datetime.now(UTC).isoformat(),
        hashlib.sha256(content).hexdigest(),
        content,
        1,
    )
    try:
        monkeypatch.setattr(
            window.device_catalog,
            "fetch",
            lambda *, should_cancel: update,
        )
        monkeypatch.setattr(window.device_catalog, "activate", lambda candidate: status)
        window.device_packs_center.identity_catalog_button.click()

        assert len(started) == 1
        assert window.device_catalog_worker is started[0]
        assert "CHECKING" in window.device_packs_center.identity_catalog_badge.text()
        started.pop().execute()
        app.processEvents()

        assert window.device_catalog_worker is None
        assert "53,575" in window.device_packs_center.identity_catalog_title.text()
        assert window.device_packs_center.identity_catalog_badge.text() == "CURRENT • READ ONLY"

        def fail(*, should_cancel):
            raise DeviceCatalogError("Official device catalog returned an unexpected route")

        monkeypatch.setattr(window.device_catalog, "fetch", fail)
        window.device_packs_center.identity_catalog_button.click()
        assert len(started) == 1
        started.pop().execute()
        app.processEvents()

        assert window.device_catalog_worker is None
        assert "sync stopped safely" in (
            window.device_packs_center.identity_catalog_title.text().casefold()
        )
        assert "No build, flash, approval, or phone action" in (
            window.device_packs_center.identity_catalog_detail.text()
        )
    finally:
        window.companion_center.transport.close()
        window.close()


def test_disabling_online_sources_cancels_pending_device_catalog_before_activation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    started = []
    activated: list[DeviceCatalogUpdate] = []
    monkeypatch.setattr("romverse.ui.main_window.start_background", started.append)
    monkeypatch.setattr(GooglePlayDeviceCatalog, "MINIMUM_ENTRIES", 1)
    existing_catalog = GooglePlayDeviceCatalog(tmp_path)
    _sync(
        existing_catalog,
        _payload(("Existing", "Existing Local", "local", "LOCAL-1")),
    )
    original_catalog = existing_catalog.catalog_path.read_bytes()
    original_receipt = existing_catalog.receipt_path.read_bytes()
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(
        None,
        logo,
        tmp_path,
        app_icon_path=logo,
        app_settings=AppSettings(online_intelligence_enabled=False),
    )
    content = _payload(("Example", "Example Nebula", "nebula", "EX-100"))
    update = DeviceCatalogUpdate(
        GOOGLE_PLAY_CATALOG_URL,
        datetime.now(UTC).isoformat(),
        hashlib.sha256(content).hexdigest(),
        content,
        1,
    )
    try:
        window.app_settings = replace(
            window.app_settings,
            online_intelligence_enabled=True,
        )
        window.device_packs_center.online_catalog_enabled = True
        monkeypatch.setattr(
            window.device_catalog,
            "fetch",
            lambda *, should_cancel: update,
        )
        monkeypatch.setattr(
            window.device_catalog,
            "activate",
            lambda candidate: activated.append(candidate),
        )

        window._refresh_device_catalog()
        worker = started.pop()
        assert window.device_catalog_worker is worker
        assert "CHECKING" in window.device_packs_center.identity_catalog_badge.text()

        with patch("romverse.ui.main_window.SettingsDialog") as dialog_type:
            dialog = dialog_type.return_value
            dialog.exec.return_value = QDialog.DialogCode.Accepted
            dialog.values.return_value = replace(
                window.app_settings,
                online_intelligence_enabled=False,
            )
            window._open_settings()

        worker.execute()
        app.processEvents()

        assert not activated
        assert window.device_catalog_worker is None
        assert window.device_catalog.catalog_path.read_bytes() == original_catalog
        assert window.device_catalog.receipt_path.read_bytes() == original_receipt
        assert window.device_catalog.search_entries("Existing Local")
        assert not window.device_catalog.search_entries("Example Nebula")
        assert window.device_packs_center.identity_catalog_badge.text() == (
            "LOCAL ONLY • ZERO AUTHORITY"
        )
        assert not window.device_packs_center.identity_catalog_button.isEnabled()
        assert window.online_status.label.text() == "LOCAL"
        assert window.active_worker is None
        assert window.rom_studio.worker is None
        assert window.guardian_center.worker is None
    finally:
        window.companion_center.transport.close()
        window.close()


def test_device_atlas_stock_gate_opens_time_machine_with_exact_context(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(
        None,
        logo,
        tmp_path,
        app_icon_path=logo,
        pack_registry=registry,
        app_settings=AppSettings(online_intelligence_enabled=False),
    )
    try:
        window._scan_complete(
            [
                AndroidDevice(
                    "private-xiaomi",
                    DeviceState.DEVICE,
                    brand="Xiaomi",
                    manufacturer="Xiaomi",
                    model="2509FPN0BC",
                    product="popsicle_global",
                    codename="popsicle",
                )
            ]
        )
        app.processEvents()

        assert window.device_packs_center.active_next_action is not None
        assert window.device_packs_center.active_next_action.route == "time_machine"
        assert "FLASH LOCKED" in window.device_packs_center.requirement_badges["flash"].text()
        window.device_packs_center.requirement_buttons["flash"].click()
        app.processEvents()

        assert window.stack.currentWidget() is window.backup_center
        assert window.backup_center.device_atlas_handoff.isVisibleTo(window.backup_center)
        assert "2509FPN0BC / popsicle" in (window.backup_center.device_atlas_handoff_title.text())
        assert "No worker or phone action started" in (
            window.backup_center.device_atlas_handoff_detail.text()
        )
        assert window.backup_center.device_atlas_project_button.isVisibleTo(window.backup_center)

        report = window.device_packs_center.active_report
        assert report is not None
        window.backup_center.device_atlas_project_button.click()
        app.processEvents()
        assert window.stack.currentWidget() is window.rom_studio
        assert window.rom_studio.dashboard_handoff_eyebrow.text().startswith("TIME MACHINE HANDOFF")
        assert report.report_digest[:16] in window.rom_studio.dashboard_handoff_detail.text()
        assert window.rom_studio.worker is None

        window._navigate_route("device_atlas")
        window.device_packs_center.requirement_buttons["flash"].click()
        app.processEvents()
        assert window.stack.currentWidget() is window.backup_center
        window._scan_complete([])
        app.processEvents()
        window.backup_center.device_atlas_project_button.click()
        app.processEvents()
        assert window.stack.currentWidget() is window.backup_center
        assert "expired safely" in window.backup_center.device_atlas_handoff_title.text()
        assert "No project worker, build, approval, or phone action started" in (
            window.backup_center.device_atlas_handoff_detail.text()
        )
    finally:
        window.companion_center.transport.close()
        window.close()


def test_device_atlas_carries_exact_pack_tools_into_forge_and_verified_archives(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(
        None,
        logo,
        tmp_path,
        app_icon_path=logo,
        pack_registry=registry,
        app_settings=AppSettings(online_intelligence_enabled=False),
    )
    setup_calls = []

    class SetupStatus:
        def setText(self, message):
            setup_calls.append(("status", message))

    class SetupDialog:
        def __init__(self, _host, statuses, _workspace, _parent, **options):
            self.status = SetupStatus()
            setup_calls.append(("statuses", statuses))
            setup_calls.append(("options", options))

        def setWindowTitle(self, title):
            setup_calls.append(("title", title))

        def exec(self):
            setup_calls.append(("exec", True))

    monkeypatch.setattr("romverse.ui.toolchain_center.ToolchainSetupDialog", SetupDialog)
    try:
        window._scan_complete(
            [
                AndroidDevice(
                    "private-xiaomi-toolchain",
                    DeviceState.DEVICE,
                    brand="Xiaomi",
                    manufacturer="Xiaomi",
                    model="2509FPN0BC",
                    product="popsicle_global",
                    codename="popsicle",
                )
            ]
        )
        app.processEvents()

        pack = window.device_packs_center.active_pack
        report = window.device_packs_center.active_report
        assert pack is not None and pack.build_contract is not None and report is not None
        assert "0/14 TOOLS VERIFIED • 14 MISSING" in (
            window.device_packs_center.requirement_badges["compile"].text()
        )
        assert "FLASH LOCKED" in window.device_packs_center.requirement_badges["flash"].text()
        window.device_packs_center.requirement_buttons["build"].click()
        assert window.stack.currentWidget() is window.rom_studio
        window._navigate_route("device_atlas")
        app.processEvents()
        window.device_packs_center.requirement_buttons["compile"].click()
        app.processEvents()

        assert window.stack.currentWidget() is window.toolchain_center
        assert not window.scanning
        assert window.active_worker is None
        assert pack.display_name in window.toolchain_center.device_pack_handoff_title.text()
        assert report.report_digest == window.toolchain_center._device_pack_context.report_digest
        assert "FLASH LOCKED" in window.toolchain_center.device_pack_handoff_badge.text()
        assert "FLASH AUTHORITY: NONE" in (
            window.toolchain_center.device_pack_handoff_feedback.text()
        )
        assert all(
            name in window.toolchain_center.device_pack_handoff_detail.text()
            for name in pack.build_contract.required_tools
        )

        window.toolchain_center.context_return_button.click()
        app.processEvents()
        assert window.stack.currentWidget() is window.device_packs_center
        assert window.device_packs_center.dashboard_handoff_eyebrow.text().startswith(
            "FORGE ARSENAL HANDOFF"
        )
        assert "Forge Arsenal" in window.device_packs_center.dashboard_handoff_title.text()
        assert report.report_digest[:16] in (
            window.device_packs_center.dashboard_handoff_detail.text()
        )
        assert "AUTHORITY NONE" in (window.device_packs_center.dashboard_handoff_detail.text())
        assert "NO ACTION STARTED" in window.device_packs_center.dashboard_handoff_detail.text()
        window.device_packs_center.requirement_buttons["compile"].click()
        app.processEvents()
        assert window.stack.currentWidget() is window.toolchain_center

        window.toolchain_center.statuses = tuple(
            ToolStatus(
                name,
                name != "AVBTool",
                "/bin/true" if name != "AVBTool" else "",
                "fixture" if name != "AVBTool" else "",
                "Ready" if name != "AVBTool" else "Missing",
            )
            for name in pack.build_contract.required_tools
        )
        window.toolchain_center._render()
        assert window.toolchain_center.context_setup_button.isEnabled()
        window.toolchain_center.context_setup_button.click()
        app.processEvents()

        options = next(value for kind, value in setup_calls if kind == "options")
        assert options["required_names"] == pack.build_contract.required_tools
        assert ("exec", True) in setup_calls

        window.toolchain_center.context_guide_button.click()
        app.processEvents()
        assert window.stack.currentWidget() is window.knowledge_center
        assert window.knowledge_center.list.currentItem().text() == (
            "Recognized device needs its exact build toolchain"
        )
        assert window.knowledge_center.source_return.text() == "Return to Forge Arsenal"
        window.knowledge_center.source_return.click()
        assert window.stack.currentWidget() is window.toolchain_center
    finally:
        window.companion_center.transport.close()
        window.close()


def test_forge_routes_missing_android_sdk_build_tools_to_exact_verified_fix(
    tmp_path: Path,
) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(
        None,
        logo,
        tmp_path,
        app_icon_path=logo,
        app_settings=AppSettings(online_intelligence_enabled=False),
    )
    try:
        window.toolchain_center.statuses = (
            ToolStatus("AAPT2", False, detail="Android SDK Build Tools not found"),
            ToolStatus("APK Signer", False, detail="Android SDK Build Tools not found"),
        )
        window.toolchain_center._render()
        window._navigate_route("forge_arsenal")
        app.processEvents()

        assert window.toolchain_center.android_sdk_guide_button.isVisibleTo(window.toolchain_center)
        window.toolchain_center.android_sdk_guide_button.click()
        app.processEvents()

        assert window.stack.currentWidget() is window.knowledge_center
        assert window.knowledge_center.list.currentItem().text() == (
            "Android SDK is installed but AAPT2 or APK Signer is still missing"
        )
        assert window.knowledge_center.source_return.text() == "Return to Forge Arsenal"
        window.knowledge_center.source_return.click()
        app.processEvents()
        assert window.stack.currentWidget() is window.toolchain_center
    finally:
        window.companion_center.transport.close()
        window.close()


def test_exact_forge_context_refuses_stale_device_and_separates_build_from_flash(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(
        None,
        logo,
        tmp_path,
        app_icon_path=logo,
        pack_registry=registry,
        app_settings=AppSettings(online_intelligence_enabled=False),
    )
    dialogs = []

    class SetupDialog:
        def __init__(self, *_args, **_kwargs):
            dialogs.append(True)

    monkeypatch.setattr("romverse.ui.toolchain_center.ToolchainSetupDialog", SetupDialog)
    device = AndroidDevice(
        "private-xiaomi-stale",
        DeviceState.DEVICE,
        brand="Xiaomi",
        manufacturer="Xiaomi",
        model="2509FPN0BC",
        product="popsicle_global",
        codename="popsicle",
    )
    try:
        window._scan_complete([device])
        app.processEvents()
        pack = window.device_packs_center.active_pack
        report = window.device_packs_center.active_report
        assert pack is not None and pack.build_contract is not None and report is not None
        assert report.build_contract_ready
        assert not report.flash_contract_ready
        window.device_packs_center.requirement_buttons["compile"].click()
        app.processEvents()

        first_digest = window.toolchain_center._device_pack_context.report_digest
        window._scan_complete([device])
        app.processEvents()
        refreshed_report = window.device_packs_center.active_report
        assert refreshed_report is not None
        assert refreshed_report.report_digest == first_digest
        assert window.toolchain_center._device_pack_context.report_digest == (
            refreshed_report.report_digest
        )
        assert "HANDOFF STOPPED" not in window.toolchain_center.device_pack_handoff_feedback.text()

        window.toolchain_center.statuses = tuple(
            ToolStatus(name, True, "/bin/true", "fixture", "Ready")
            for name in pack.build_contract.required_tools
        )
        window.toolchain_center._render()
        assert window.toolchain_center.context_continue_button.isEnabled()
        assert "FLASH LOCKED" in window.toolchain_center.device_pack_handoff_badge.text()
        window.toolchain_center.context_continue_button.click()
        assert window.stack.currentWidget() is window.rom_studio
        assert window.rom_studio.dashboard_handoff_eyebrow.text().startswith(
            "FORGE ARSENAL HANDOFF"
        )
        assert window.rom_studio.command_tabs.currentIndex() == 1
        assert first_digest[:16] in window.rom_studio.dashboard_handoff_detail.text()
        assert "NO BUILD, APPROVAL, FLASH, OR PHONE ACTION STARTED" in (
            window.rom_studio.dashboard_handoff_detail.text()
        )
        assert window.rom_studio.worker is None

        window.device_packs_center.requirement_buttons["compile"].click()
        app.processEvents()
        window.toolchain_center.statuses = (ToolStatus("Python", False, detail="Missing fixture"),)
        window.toolchain_center._render()
        assert window.toolchain_center.context_setup_button.isEnabled()
        window._scan_complete([])
        app.processEvents()
        window.toolchain_center.context_return_button.click()
        assert window.stack.currentWidget() is window.toolchain_center
        window.toolchain_center.context_setup_button.click()

        assert dialogs == []
        assert window.stack.currentWidget() is window.toolchain_center
        assert "DEVICE PACK HANDOFF STOPPED" in (
            window.toolchain_center.device_pack_handoff_feedback.text()
        )
        assert "NO INSTALL, BUILD, OR PHONE ACTION STARTED" in (
            window.toolchain_center.device_pack_handoff_feedback.text()
        )
        window.toolchain_center._render()
        assert not window.toolchain_center.context_setup_button.isEnabled()
        assert "STALE CONTEXT" in window.toolchain_center.device_pack_handoff_badge.text()
    finally:
        window.companion_center.transport.close()
        window.close()


def test_adb_tool_refresh_activates_and_revokes_every_dependent_runtime(
    tmp_path: Path,
    monkeypatch,
) -> None:
    QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(None, logo, tmp_path, app_icon_path=logo)
    scans: list[bool] = []
    monkeypatch.setattr(window, "scan", lambda: scans.append(True))
    runtime = Path(sys.executable).resolve()
    available = (ToolStatus("ADB", True, str(runtime), "test", "Ready"),)
    missing = (ToolStatus("ADB", False, detail="Missing"),)
    device = AndroidDevice("device-serial", DeviceState.DEVICE, model="Test phone")
    runtime_requests = []

    def resolve_runtime(required, **options):
        runtime_requests.append((required, options))
        return False

    monkeypatch.setattr(window.rom_studio, "_resolve_required_tools", resolve_runtime)

    try:
        window.apk_installer.runtime_tools_requested.emit()
        assert runtime_requests[0][0] == ("ADB",)
        assert runtime_requests[0][1]["parent"] is window

        window.device_center.runtime_tools_requested.emit()
        window.terminal_center.runtime_tools_requested.emit()
        window.repair_center.runtime_tools_requested.emit()
        window.backup_center.runtime_tools_requested.emit()
        assert [request[0] for request in runtime_requests] == [
            ("ADB",),
            ("ADB",),
            ("ADB",),
            ("ADB",),
            ("ADB",),
        ]

        window.rom_studio.tool_statuses_resolved.emit(available)

        assert window.engine is not None
        assert window.timer.isActive()
        assert scans == [True]
        resolved_adb = runtime
        assert window.rom_studio.adb_executable == resolved_adb
        assert window.rom_studio.device_scan_available
        assert window.apk_installer.install_service is not None
        assert window.backup_center.media_backup_service is not None
        assert window.terminal_center.adb_executable == resolved_adb
        assert window.repair_center.host_repair_service is not None

        window._scan_complete([device])
        assert window.repair_center.devices

        window._tool_statuses_changed(missing)

        assert window.engine is None
        assert not window.timer.isActive()
        assert not window._reconnect_timer.isActive()
        assert window.rom_studio.adb_executable is None
        assert not window.rom_studio.device_scan_available
        assert window.apk_installer.install_service is None
        assert window.backup_center.media_backup_service is None
        assert window.terminal_center.adb_executable is None
        assert window.repair_center.host_repair_service is None
        assert window.device_center.devices == []
        assert window.diagnostics_center.devices == []
        assert window.repair_center.devices == []
        assert window.rom_studio.devices == []
        assert "Platform Tools" in window.device_center.device_note.text()
    finally:
        window.companion_center.transport.close()
        window.close()


def test_smart_solution_routes_to_exact_platform_tools_review_without_running_it(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(None, logo, tmp_path, app_icon_path=logo)
    fingerprint = ErrorFingerprint.create("fastboot command not found exit code 127")
    receipt = OnlineRemediationService(tmp_path).lookup(fingerprint)
    lead = receipt.candidates[0]
    assert lead.local_action_id == "verify-platform-tools"
    binding = (
        lead.local_action_id,
        receipt.fingerprint.fingerprint_id,
        receipt.receipt_digest,
        lead.source_id,
    )
    monkeypatch.setattr(
        window.repair_center,
        "validate_solution_handoff",
        lambda *values: values == binding,
    )
    monkeypatch.setattr(
        window.repair_center,
        "solution_handoff_receipt",
        lambda *values: receipt if values == binding else None,
    )

    try:
        window.repair_center.solution_action_requested.emit(*binding)
        app.processEvents()

        context = window.toolchain_center._repair_solution_context
        assert context is not None
        assert context.required_tools == ("ADB", "Fastboot")
        assert window.stack.currentWidget() is window.toolchain_center
        assert not window.toolchain_center.device_pack_handoff.isHidden()
        assert "RECOVERY BAY SMART SOLUTION" in (
            window.toolchain_center.device_pack_handoff_eyebrow.text()
        )
        assert "PHONE AUTHORITY: NONE" in (window.toolchain_center.device_pack_handoff_badge.text())
        assert window.rom_studio.worker is None
        assert window.repair_center.host_repair_worker is None

        adb = tmp_path / "verified-adb"
        fastboot = tmp_path / "verified-fastboot"
        adb.write_bytes(b"adb fixture")
        fastboot.write_bytes(b"fastboot fixture")
        window.toolchain_center.statuses = (
            ToolStatus("ADB", True, str(adb), "fixture", "Ready"),
            ToolStatus("Fastboot", True, str(fastboot), "fixture", "Ready"),
        )
        window.toolchain_center._record_repair_solution_outcome()

        decision = OnlineRemediationService(tmp_path).synthesize(receipt)
        assert lead.source_id in decision.locally_verified_source_ids
        assert window.toolchain_center._repair_solution_outcome_saved
        assert "OUTCOME VERIFIED AND SAVED" in (
            window.toolchain_center.device_pack_handoff_feedback.text()
        )
    finally:
        window.companion_center.transport.close()
        window.close()


def test_fastboot_only_tool_refresh_keeps_read_only_identity_scanning_available(
    tmp_path: Path,
    monkeypatch,
) -> None:
    QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(None, logo, tmp_path, app_icon_path=logo)
    scans: list[bool] = []
    monkeypatch.setattr(window, "scan", lambda: scans.append(True))
    available = (
        ToolStatus("ADB", False, detail="Missing"),
        ToolStatus("Fastboot", True, str(Path(sys.executable).resolve()), "test", "Ready"),
    )

    try:
        window._tool_statuses_changed(available)

        assert window.engine is not None
        assert window.engine.adb is None
        assert window.engine.fastboot is not None
        assert window.timer.isActive()
        assert scans == [True]
        assert window.rom_studio.adb_executable is None
        assert window.rom_studio.device_scan_available
        assert window.apk_installer.install_service is None
        assert window.backup_center.media_backup_service is None
        assert window.terminal_center.adb_executable is None
        assert window.repair_center.host_repair_service is None
    finally:
        window.companion_center.transport.close()
        window.close()


def test_fastboot_scan_connects_command_deck_to_exact_device_atlas_pack(
    tmp_path: Path,
) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
    window = MainWindow(
        None,
        logo,
        tmp_path,
        app_icon_path=logo,
        pack_registry=registry,
        app_settings=AppSettings(online_intelligence_enabled=False),
    )
    fastboot = AndroidDevice(
        "private-fastboot",
        DeviceState.BOOTLOADER,
        transport="usb-fastboot",
        model="popsicle",
        product="popsicle",
        codename="popsicle",
        bootloader_locked=False,
        fastboot_capability="Observed bootloader fastboot transport",
        connection_note="Connected in bootloader fastboot mode with read-only identity evidence.",
    )

    try:
        window._scan_complete([fastboot])
        app.processEvents()

        assert window.connection_state.text() == "⌁  Connected via Bootloader"
        assert window.device_center.devices[0].marketing_name == "Xiaomi 17 Pro Max"
        assert window.device_packs_center.active_pack is not None
        assert window.device_packs_center.active_pack.pack_id == (
            "xiaomi.popsicle.hyperos4.os4.0.0.23"
        )

        window.device_center.next_button.click()
        app.processEvents()

        assert window.stack.currentWidget() is window.device_packs_center
        assert window.device_packs_center.active_report is not None
        assert window.device_packs_center.active_report.build_contract_ready
        assert not window.device_packs_center.active_report.flash_contract_ready
    finally:
        window.companion_center.transport.close()
        window.close()


def test_device_scan_failure_copy_names_the_real_subsystem() -> None:
    assert _device_scan_failure_copy("Guardian audit integrity check failed: record capacity") == (
        "⌁  Guardian evidence needs attention",
        "●  Guardian ledger needs attention",
        "Evidence verification paused the scan • ROMVERSE will retry safely",
    )
    assert (
        "ADB service is restarting"
        in _device_scan_failure_copy("ADB server version mismatch; daemon restarted")[0]
    )
    assert "USB permission" in _device_scan_failure_copy("permission denied opening USB")[0]
    assert _device_scan_failure_is_transient("ADB transport failed during refresh")
    assert _device_scan_failure_is_transient("probe timed out")
    assert not _device_scan_failure_is_transient("Guardian audit integrity failed")


def test_sidebar_navigation_tooltip_is_compact_wrapped_and_escaped() -> None:
    tooltip = _sidebar_nav_tooltip("App <Launchpad>", "Install Android apps & packages.")

    assert tooltip.startswith("<qt>")
    assert "width='220'" in tooltip
    assert tooltip.count("<tr>") == 2
    assert "App &lt;Launchpad&gt;" in tooltip
    assert "apps &amp; packages" in tooltip


def test_sidebar_reserves_navigation_space_and_folds_optional_connection_fields(
    tmp_path: Path,
) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(None, logo, tmp_path, app_icon_path=logo)
    try:
        window.resize(1080, 700)
        window.show()
        app.processEvents()

        assert window._brand_card.height() <= 190
        assert not window._brand_logo.pixmap().isNull()
        assert window._brand_logo.accessibleName() == (
            "Official ROMVERSE website icon in the app sidebar"
        )
        assert window.nav_scroll.minimumHeight() == 150
        assert window.sidebar_device_state.wordWrap()
        assert not window.connection_uptime.isVisible()
        assert not window.connection_clock.isVisible()

        window.resize(1440, 900)
        app.processEvents()
        assert window._brand_card.height() <= 250
        assert window.connection_uptime.isVisible()
        assert window.connection_clock.isVisible()
    finally:
        window.companion_center.transport.close()
        window.close()


def test_workspace_chrome_collapses_focuses_and_restores_without_changing_page_state(
    tmp_path: Path,
) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(None, logo, tmp_path, app_icon_path=logo)
    try:
        window.resize(1200, 760)
        window.show()
        window._navigate_route("about")
        app.processEvents()
        page_index = window.stack.currentIndex()
        page = window.stack.currentWidget()

        assert window.workspace_section.text() == "SYSTEM"
        assert window.workspace_route_title.text() == "About ROMVERSE"
        assert window.workspace_route_title.accessibleName() == (
            "Current Desktop page: About ROMVERSE"
        )
        assert window.workspace_search_button.toolTip().startswith("Find any ROMVERSE page")

        window.navigation_toggle.click()
        app.processEvents()

        assert window._workspace_shell_state.navigation_collapsed
        assert window.sidebar.width() == 78
        assert window._brand_card.height() == 68
        assert window._brand_logo.width() == window._brand_logo.height() == 58
        assert all(label.isHidden() for label in window.nav_section_labels)
        assert window.sidebar_device_card.isHidden()
        assert window.sidebar_version.isHidden()
        assert all(not button.text() for button in window.nav_buttons)
        assert all(button.accessibleName().startswith("Open ") for button in window.nav_buttons)
        assert window.stack.currentIndex() == page_index
        assert window.stack.currentWidget() is page
        assert window.sidebar.isVisible()
        assert window.connection_bar.isVisible()

        window.focus_button.click()
        app.processEvents()

        assert window._workspace_shell_state.focus_mode
        assert window.sidebar.isHidden()
        assert window.connection_bar.isHidden()
        assert window.workspace_bar.isVisible()
        assert not window.navigation_toggle.isEnabled()
        assert window.navigation_toggle.isHidden()
        assert window.focus_exit_shortcut.isEnabled()
        assert window.focus_button.text().startswith("EXIT FOCUS")
        assert window.workspace_section.text() == "FOCUS WORKSPACE  •  SYSTEM"
        assert window.stack.currentIndex() == page_index
        assert window.stack.currentWidget() is page

        window.workspace_search_button.click()
        app.processEvents()
        assert window._command_palette is not None and window._command_palette.isVisible()
        window._command_palette.reject()
        app.processEvents()
        assert window._command_palette is None

        window._leave_focus_mode()
        app.processEvents()

        assert not window._workspace_shell_state.focus_mode
        assert window._workspace_shell_state.navigation_collapsed
        assert window.sidebar.isVisible() and window.sidebar.width() == 78
        assert window.connection_bar.isVisible()
        assert window.workspace_section.text() == "SYSTEM"

        window.navigation_toggle.click()
        app.processEvents()
        assert window.sidebar.width() == 263
        assert [button.text().replace("&&", "&") for button in window.nav_buttons][0] == (
            "Command Deck"
        )
        assert not any(label.isHidden() for label in window.nav_section_labels)
        assert window.sidebar_device_card.isVisible()
    finally:
        window.companion_center.transport.close()
        window.close()


def test_sidebar_product_art_never_mislabels_another_android_device(tmp_path: Path) -> None:
    QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(None, logo, tmp_path, app_icon_path=logo)
    samsung = AndroidDevice(
        "private-serial",
        DeviceState.DEVICE,
        manufacturer="Samsung",
        model="SM-S938B",
        marketing_name="Galaxy S25 Ultra",
        codename="pa3q",
    )
    xiaomi = AndroidDevice(
        "private-serial",
        DeviceState.DEVICE,
        manufacturer="Xiaomi",
        model="2509FPN0BC",
        marketing_name="Xiaomi 17 Pro Max",
        codename="popsicle",
    )
    try:
        assert _sidebar_device_art_kind(samsung) == "generic-android"
        window._set_sidebar_device_art(samsung)
        assert "Generic Android" in window.sidebar_device_image.accessibleName()
        assert "Samsung Galaxy S25 Ultra" in window.sidebar_device_image.toolTip()
        assert "unconfirmed" in window.sidebar_device_image.toolTip()

        assert _sidebar_device_art_kind(xiaomi) == "xiaomi-17-pro-max"
        window._set_sidebar_device_art(xiaomi)
        assert "Verified product image" in window.sidebar_device_image.accessibleName()
        assert "Xiaomi 17 Pro Max" in window.sidebar_device_image.toolTip()
        assert "exact Device DNA artwork" in window.sidebar_device_image.toolTip()
    finally:
        window.companion_center.transport.close()
        window.close()
