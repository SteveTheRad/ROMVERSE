from __future__ import annotations

import json
import os
from importlib.resources import files
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication, QLabel

from romverse.core.activity import ActivityStore
from romverse.core.settings import AppSettings
from romverse.device.models import AndroidDevice, DeviceState, StorageInfo
from romverse.device_packs.registry import DevicePackRegistry
from romverse.device_packs.validation import DevicePackValidationService
from romverse.repair.autopilot import (
    RecoveryAutopilotContext,
    RecoveryAutopilotService,
    RecoveryRouteKind,
    RecoveryTrigger,
)
from romverse.rom.projects import RomProjectStore
from romverse.ui.backup_center import BackupCenter, TimeMachineWorker
from romverse.ui.main_window import MainWindow
from romverse.ui.theme import STYLESHEET
from tests.test_recovery_autopilot import _device as _recovery_device
from tests.test_recovery_autopilot import _registry as _recovery_registry


def _xiaomi_readiness_report():
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
    device = AndroidDevice(
        "private-readiness",
        DeviceState.DEVICE,
        manufacturer="Xiaomi",
        model="2509FPN0BC",
        product="popsicle_global",
        codename="popsicle",
    )
    pack = registry.resolve(device).pack
    assert pack is not None
    return DevicePackValidationService().assess(pack, device)


def _recovery_time_machine_context(tmp_path: Path):
    source = tmp_path / "exact-stock.zip"
    source.write_bytes(b"exact stock package fixture")
    workspace = tmp_path / "workspace"
    store = RomProjectStore(workspace)
    project = store.create("Exact Recovery Project", "test.recovery")
    project = store.import_original(project.project_id, source)
    service = RecoveryAutopilotService(workspace, _recovery_registry())
    incident = service.start(
        RecoveryAutopilotContext(
            RecoveryTrigger.BOOTLOOP,
            device=_recovery_device(DeviceState.FASTBOOT, boot_completed=False),
            project_id=project.project_id,
        )
    )
    route = next(
        item for item in incident.routes if item.kind is RecoveryRouteKind.EXACT_STOCK_RESTORE
    )
    assert route.owner_route == "time_machine"
    return source, workspace, project, incident, route


def test_time_machine_carries_recovery_context_to_exact_evidence_and_back(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    source, workspace, project, incident, route = _recovery_time_machine_context(tmp_path)
    center = BackupCenter(workspace)
    returned: list[tuple[str, str]] = []
    center.recovery_requested.connect(
        lambda incident_id, route_id: returned.append((incident_id, route_id))
    )

    assert center.open_recovery_review(incident, route)
    app.processEvents()

    assert center.recovery_review_identity == (incident.incident_id, route.route_id)
    assert center.recovery_review.isVisibleTo(center)
    assert center.recovery_review.objectName() == "TimeMachineRecoveryReviewCard"
    assert "QFrame#TimeMachineRecoveryReviewCard" in STYLESHEET
    assert center.project_selector.currentData() == project.project_id
    assert not center.project_selector.isEnabled()
    assert center.recovery_backup_button.isEnabled()
    assert center.recovery_stock_button.isEnabled()
    assert center.recovery_reverify_button.isEnabled()
    detail = center.recovery_review_detail.text()
    assert incident.incident_id[:12] in detail
    assert incident.pack_id in detail
    assert project.project_id in detail
    assert project.original is not None
    assert project.original.sha256[:16] in detail
    assert route.summary in detail
    assert "File selection and hashing only" in detail
    assert "Execution: none" in detail
    assert "Phone changed: no" in detail
    assert "Bootloader relock: never" in detail
    assert center.evidence_worker is None
    assert not incident.phone_changed

    center.recovery_return_button.click()
    assert returned == [(incident.incident_id, route.route_id)]
    assert source.read_bytes() == b"exact stock package fixture"
    center.close()


def test_time_machine_returns_ready_evidence_to_recovery_after_verification(
    tmp_path, monkeypatch
) -> None:
    app = QApplication.instance() or QApplication([])
    source, workspace, project, incident, route = _recovery_time_machine_context(tmp_path)
    center = BackupCenter(workspace)
    center.recovery_evidence.register(project.project_id, "external_backup", source)
    queued = []
    monkeypatch.setattr("romverse.ui.backup_center.start_background", queued.append)
    returned: list[tuple[str, str]] = []
    center.recovery_requested.connect(
        lambda incident_id, route_id: returned.append((incident_id, route_id))
    )
    assert center.open_recovery_review(incident, route)

    center._start_recovery_evidence(
        "register",
        project.project_id,
        "stock_recovery",
        source,
    )
    assert len(queued) == 1
    queued.pop().run()
    app.processEvents()

    assessment = center.recovery_review_assessment(incident.incident_id, route.route_id)
    assert assessment is not None and assessment.ready
    assert center.recovery_review_badge.text() == "EVIDENCE READY • ZERO AUTHORITY"
    assert returned == [(incident.incident_id, route.route_id)]
    assert center.evidence_worker is None
    assert source.read_bytes() == b"exact stock package fixture"
    assert not incident.phone_changed
    center.close()


def test_time_machine_explains_device_atlas_stock_gate_without_inventing_project(
    tmp_path,
) -> None:
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(STYLESHEET)
    center = BackupCenter(tmp_path)
    report = _xiaomi_readiness_report()
    requested: list[tuple[str, str]] = []
    center.rom_studio_requested.connect(
        lambda report_id, digest: requested.append((report_id, digest))
    )

    assert center.open_device_atlas_readiness(report)
    app.processEvents()

    assert center.device_atlas_handoff.isVisibleTo(center)
    assert "Stock recovery evidence needed" in center.device_atlas_handoff_title.text()
    assert "Create or import" in center.device_atlas_handoff_detail.text()
    assert "No worker or phone action started" in center.device_atlas_handoff_detail.text()
    assert center.device_atlas_project_button.isVisibleTo(center)
    assert center.snapshot_list.palette().color(QPalette.ColorRole.Base).lightness() < 64
    center.device_atlas_project_button.click()
    assert requested == [(report.report_id, report.report_digest)]
    center.close()


def test_time_machine_empty_state_opens_rom_studio_at_project_creation(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(
        None,
        logo,
        tmp_path,
        app_icon_path=logo,
        app_settings=AppSettings(online_intelligence_enabled=False),
    )
    window.resize(1_440, 900)
    window.show()
    try:
        assert window._navigate_route("time_machine")
        app.processEvents()

        assert window.backup_center.local_setup.isVisibleTo(window.backup_center)
        assert window.backup_center.local_setup_button.isEnabled()
        assert window.backup_center.local_setup_button.text() == "Create project in ROM Studio"

        window.backup_center.local_setup_button.click()
        app.processEvents()

        assert window.stack.currentWidget() is window.rom_studio
        assert window.rom_studio.dashboard_handoff.isVisibleTo(window.rom_studio)
        assert window.rom_studio.dashboard_handoff_eyebrow.text().startswith("TIME MACHINE HANDOFF")
        assert "no dialog or worker was started automatically" in (
            window.rom_studio.dashboard_handoff_detail.text().casefold()
        )
        assert window.rom_studio.new_button.hasFocus()
        assert window.rom_studio.worker is None
        assert window.backup_center.worker is None
        assert not window.rom_studio.store.list_projects()
    finally:
        window.companion_center.transport.close()
        window.close()


def test_time_machine_project_without_snapshot_opens_exact_studio_prerequisite(
    tmp_path,
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
    project = window.rom_studio.store.create("Recovery baseline project")
    window.resize(1_440, 900)
    window.show()
    try:
        assert window._navigate_route("time_machine")
        app.processEvents()

        assert window.backup_center.project_selector.currentData() == project.project_id
        assert window.backup_center.local_setup.isVisibleTo(window.backup_center)
        assert window.backup_center.local_setup_button.text() == ("Prepare baseline in ROM Studio")

        window.backup_center.local_setup_button.click()
        app.processEvents()

        assert window.stack.currentWidget() is window.rom_studio
        assert window.rom_studio.current_project is not None
        assert window.rom_studio.current_project.project_id == project.project_id
        assert window.rom_studio.import_button.hasFocus()
        assert project.project_id in window.rom_studio.dashboard_handoff_detail.text()
        assert "IMPORT ORIGINAL" in window.rom_studio.dashboard_handoff_badge.text()
        assert window.rom_studio.worker is None
        assert window.backup_center.worker is None
    finally:
        window.companion_center.transport.close()
        window.close()


def test_time_machine_refuses_stale_empty_setup_handoff_in_page(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(
        None,
        logo,
        tmp_path,
        app_icon_path=logo,
        app_settings=AppSettings(online_intelligence_enabled=False),
    )
    window.resize(1_440, 900)
    window.show()
    try:
        assert window._navigate_route("time_machine")
        app.processEvents()
        assert window.backup_center.project_selector.currentData() is None

        window.rom_studio.store.create("Externally appeared project")
        window.backup_center.local_setup_button.click()
        app.processEvents()

        assert window.stack.currentWidget() is window.backup_center
        assert "ROM STUDIO SETUP HANDOFF STOPPED" in window.backup_center.local_result.text()
        assert "No project worker, snapshot, restore, build, or phone action started" in (
            window.backup_center.local_result.text()
        )
        assert window.backup_center.project_selector.count() == 1
        assert window.rom_studio.worker is None
        assert window.backup_center.worker is None
    finally:
        window.companion_center.transport.close()
        window.close()


def test_time_machine_binds_device_atlas_handoff_to_existing_project(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    source = tmp_path / "protected-stock.zip"
    source.write_bytes(b"protected stock fixture")
    store = RomProjectStore(tmp_path)
    project = store.import_original(store.create("Exact stock project").project_id, source)
    center = BackupCenter(tmp_path)

    assert center.open_device_atlas_readiness(_xiaomi_readiness_report())
    app.processEvents()

    assert center.project_selector.currentData() == project.project_id
    assert "Exact stock project is selected" in center.device_atlas_handoff_detail.text()
    assert not center.device_atlas_project_button.isVisible()
    assert center.stock_evidence_button.isEnabled()
    center.close()


def test_time_machine_console_lists_and_verifies_local_baseline_snapshots(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    source = tmp_path / "baseline.img"
    source.write_bytes(b"verified baseline" * 100)
    workspace = tmp_path / "workspace"
    store = RomProjectStore(workspace)
    project = store.create("Recovery console")
    store.import_original(project.project_id, source)
    store.create_working_copy(project.project_id)
    snapshot = store.create_snapshot(project.project_id)

    center = BackupCenter(workspace)
    app.processEvents()
    assert center.project_selector.count() == 1
    assert center.snapshot_list.count() == 1
    assert center.verify_snapshot_button.isEnabled()
    assert center.restore_snapshot_button.isEnabled()
    assert snapshot.sha256 in center.snapshot_detail.text()
    assert any("phone partitions" in label.text() for label in center.findChildren(QLabel))

    completed = []
    progress = []
    worker = TimeMachineWorker(store, "verify", project.project_id, snapshot)
    worker.signals.complete.connect(completed.append)
    worker.signals.progress.connect(progress.append)
    worker.run()
    assert completed[0].valid
    assert progress[0] == 0
    assert progress[-1] == 100
    assert progress == sorted(set(progress))
    center.close()


def test_time_machine_restore_worker_reports_real_monotonic_progress(tmp_path) -> None:
    QApplication.instance() or QApplication([])
    source = tmp_path / "restore-baseline.img"
    source.write_bytes(b"restore baseline" * 100)
    store = RomProjectStore(tmp_path / "workspace")
    project = store.import_original(store.create("Measured restore").project_id, source)
    working = store.create_working_copy(project.project_id)
    snapshot = store.create_snapshot(project.project_id)
    (store.workspace / working.workspace_path).write_bytes(b"changed local workspace")
    completed = []
    progress = []
    worker = TimeMachineWorker(store, "restore", project.project_id, snapshot)
    worker.signals.complete.connect(completed.append)
    worker.signals.progress.connect(progress.append)

    worker.run()

    assert completed
    assert completed[0]["verified"] is True
    assert progress[0] == 0
    assert progress[-1] == 100
    assert progress == sorted(set(progress))
    assert store.load_latest_restore_receipt(project.project_id) is not None


def test_time_machine_explains_legacy_snapshot_and_unlocks_restore_after_verify(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    source = tmp_path / "baseline.img"
    source.write_bytes(b"legacy baseline" * 100)
    workspace = tmp_path / "workspace"
    store = RomProjectStore(workspace)
    project = store.import_original(store.create("Legacy snapshot").project_id, source)
    store.create_working_copy(project.project_id)
    snapshot = store.create_snapshot(project.project_id)
    record = store.snapshots_root / project.project_id / f"{snapshot.snapshot_id}.romverse"
    payload = json.loads(record.read_text())
    record.write_text(
        json.dumps(
            {
                key: value
                for key, value in payload.items()
                if key
                in {
                    "snapshot_id",
                    "project_id",
                    "workspace_path",
                    "sha256",
                    "size_bytes",
                    "created_at",
                }
            }
        ),
        encoding="utf-8",
    )

    center = BackupCenter(workspace)
    app.processEvents()

    assert "LEGACY • VERIFY" in center.snapshot_list.currentItem().text()
    assert "full verification required" in center.snapshot_detail.text()
    assert center.verify_snapshot_button.isEnabled()
    assert not center.restore_snapshot_button.isEnabled()

    assert store.verify_snapshot(store.list_snapshots(project.project_id)[0]).valid
    center.refresh_local_snapshots(project.project_id)
    app.processEvents()

    assert "CURRENT • READY" in center.snapshot_list.currentItem().text()
    assert center.restore_snapshot_button.isEnabled()
    center.close()


def test_time_machine_accepts_live_string_verified_boot_and_records_real_plan(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    center = BackupCenter(tmp_path)
    device = AndroidDevice(
        serial="private-serial",
        state=DeviceState.DEVICE,
        manufacturer="Xiaomi",
        model="Test Phone",
        build_id="BUILD.1",
        battery_percent=90,
        storage=StorageInfo(percent_used=30),
        bootloader_locked=True,
        verified_boot="green",
    )

    center.set_devices([device])
    with patch("romverse.ui.backup_center.QMessageBox.information"):
        center._create_plan()
    app.processEvents()

    assert center.plan_button.isEnabled()
    assert center.review_button.isEnabled()
    assert "no phone data copied" in center.result.text()
    assert center.plan_store.load_latest().integrity_verified
    center.close()


def test_time_machine_activity_reopens_exact_plan_and_snapshot_evidence(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    activity = ActivityStore(tmp_path)
    center = BackupCenter(tmp_path, activity)
    device = AndroidDevice(
        serial="private-serial",
        state=DeviceState.DEVICE,
        manufacturer="Xiaomi",
        model="Test Phone",
        battery_percent=90,
        storage=StorageInfo(percent_used=30),
        bootloader_locked=True,
        verified_boot="green",
    )
    center.set_devices([device])
    with patch("romverse.ui.backup_center.QMessageBox.information"):
        center._create_plan()
    plan_event = activity.list_recent()[0]
    assert plan_event.context_type == "backup-plan"
    assert center.open_backup_plan(plan_event.context_id)
    assert center.plan_context.isVisibleTo(center)
    assert plan_event.context_id in center.plan_context_detail.text()
    assert "no action started" in center.plan_context_detail.text()

    source = tmp_path / "baseline.img"
    source.write_bytes(b"verified baseline" * 100)
    project = center.rom_store.import_original(
        center.rom_store.create("Activity snapshot").project_id,
        source,
    )
    center.rom_store.create_working_copy(project.project_id)
    snapshot = center.rom_store.create_snapshot(project.project_id)
    center.refresh_local_snapshots(project.project_id)
    center.worker = TimeMachineWorker(center.rom_store, "verify", project.project_id, snapshot)
    center._time_machine_complete(center.rom_store.verify_snapshot(snapshot))
    app.processEvents()

    snapshot_event = activity.list_recent()[0]
    assert snapshot_event.context_type == "time-machine-snapshot"
    assert snapshot_event.context_id == f"{project.project_id}.{snapshot.snapshot_id}"
    assert center.open_snapshot(project.project_id, snapshot.snapshot_id)
    assert center.snapshot_list.currentItem().data(Qt.ItemDataRole.UserRole) == snapshot.snapshot_id
    assert "no restore or phone action started" in center.local_result.text()
    center.close()


def test_time_machine_emits_only_the_exact_verified_guardian_plan_identity(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    center = BackupCenter(tmp_path)
    center.set_devices(
        [
            AndroidDevice(
                serial="private-serial",
                state=DeviceState.DEVICE,
                manufacturer="Xiaomi",
                model="Test Phone",
                battery_percent=90,
                storage=StorageInfo(percent_used=30),
                bootloader_locked=True,
                verified_boot="green",
            )
        ]
    )
    with patch("romverse.ui.backup_center.QMessageBox.information"):
        center.plan_button.click()
    loaded = center.plan_store.load_latest()
    assert loaded.data is not None
    requested: list[tuple[str, str]] = []
    center.guardian_requested.connect(lambda plan_id, digest: requested.append((plan_id, digest)))

    center.guardian_button.click()
    app.processEvents()

    assert requested == [(loaded.data["plan_id"], loaded.data["plan_digest"])]
    assert "Approval: none" in center.result.text()
    assert "Execution: none" in center.result.text()
    center.close()


def test_time_machine_refuses_a_plan_tampered_after_it_was_enabled(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    center = BackupCenter(tmp_path)
    center.set_devices(
        [
            AndroidDevice(
                serial="private-serial",
                state=DeviceState.DEVICE,
                manufacturer="Xiaomi",
                model="Test Phone",
                battery_percent=90,
                storage=StorageInfo(percent_used=30),
            )
        ]
    )
    with patch("romverse.ui.backup_center.QMessageBox.information"):
        center.plan_button.click()
    requested: list[tuple[str, str]] = []
    center.guardian_requested.connect(lambda plan_id, digest: requested.append((plan_id, digest)))
    data = json.loads(center.plan_store.latest_path.read_text(encoding="utf-8"))
    data["phone_data_copied"] = True
    center.plan_store.latest_path.write_text(json.dumps(data), encoding="utf-8")

    center.guardian_button.click()
    app.processEvents()

    assert requested == []
    assert not center.guardian_button.isEnabled()
    assert "GUARDIAN HANDOFF STOPPED" in center.result.text()
    assert "No review context or action was created" in center.result.text()
    center.close()


def test_time_machine_resolves_runtime_in_place_before_real_local_backup(
    tmp_path, monkeypatch
) -> None:
    app = QApplication.instance() or QApplication([])
    center = BackupCenter(tmp_path)
    device = AndroidDevice(
        serial="private-serial",
        state=DeviceState.DEVICE,
        manufacturer="Xiaomi",
        model="Test Phone",
        build_id="BUILD.1",
        battery_percent=90,
        storage=StorageInfo(percent_used=30),
    )

    assert not center.phone_backup_button.isEnabled()
    center.set_devices([device])
    app.processEvents()
    assert center.phone_backup_button.isEnabled()
    assert "Resolve Platform Tools" in center.phone_backup_button.text()
    requested = []
    prepared = []
    monkeypatch.setattr(center, "_prepare_phone_backup", lambda: prepared.append(True))
    center.runtime_tools_requested.connect(
        lambda: (
            requested.append(True),
            center.set_media_backup_service(object()),  # type: ignore[arg-type]
        )
    )

    center.phone_backup_button.click()
    app.processEvents()

    assert requested == [True]
    assert prepared == [True]
    assert "Back up phone" in center.phone_backup_button.text()
    assert "choose a local destination" in center.phone_backup_result.text().casefold()

    center.set_media_backup_service(None)
    app.processEvents()
    assert center.phone_backup_button.isEnabled()
    assert "resolve platform tools" in center.phone_backup_button.text().casefold()
    assert "continue directly" in center.phone_backup_result.text().casefold()
    center.close()


def test_project_vault_ui_captures_compares_branches_and_exports_without_phone_action(
    tmp_path,
    monkeypatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    source = tmp_path / "vault-firmware.img"
    source.write_bytes(b"vault firmware" * 100)
    workspace = tmp_path / "workspace"
    store = RomProjectStore(workspace)
    project = store.import_original(store.create("Vault UI").project_id, source)
    store.create_working_copy(project.project_id)
    tree = store.working_root / project.project_id / "tree"
    tree.mkdir(parents=True)
    (tree / "build.prop").write_text("ro.test=one\n", encoding="utf-8")
    activity = ActivityStore(workspace)
    center = BackupCenter(workspace, activity)
    queued = []
    monkeypatch.setattr("romverse.ui.backup_center.start_background", queued.append)

    center._start_vault_worker(
        "capture",
        label="Known working",
        reason="Before the local experiment",
    )
    queued.pop(0).run()
    app.processEvents()
    assert center.vault_selector.count() == 1
    assert "Known working" in center.vault_selector.currentText()
    assert "phone untouched" in center.vault_result.text()
    assert center.vault_timeline.accessibleDescription().startswith("1 checkpoint")
    event = activity.list_recent()[0]
    assert event.context_type == "project-vault-entry"
    assert center.open_vault_entry(project.project_id, event.context_id.rsplit(".", 1)[1])
    assert "no restore or phone action started" in center.vault_result.text()

    (tree / "build.prop").write_text("ro.test=two\n", encoding="utf-8")
    center._start_vault_worker(
        "capture",
        label="Property experiment",
        reason="After a measured local property change",
        kind="experiment",
    )
    queued.pop(0).run()
    app.processEvents()
    assert center.vault_selector.count() == 2
    assert center.restore_vault_state_button.isEnabled()
    center._compare_vault_entry()
    assert "Changed (1)" in center.vault_result.text()
    assert "no project file or phone was changed" in center.vault_result.text()

    selected = center._selected_vault_entry()
    assert selected is not None
    center._start_vault_worker("branch", entry=selected, branch_name="Safe branch")
    queued.pop(0).run()
    app.processEvents()
    assert len(center.vault_branches) == 1
    assert "known-working project baseline not overwritten" in center.vault_result.text()

    capsule = tmp_path / "vault-ui.romverse.zip"
    selected = center._selected_vault_entry()
    assert selected is not None
    center._start_vault_worker("export", entry=selected, destination=capsule)
    queued.pop(0).run()
    app.processEvents()
    assert capsule.is_file()
    assert "EXPORTED AND REVERIFIED" in center.vault_result.text()
    assert "nothing published" in center.vault_result.text()
    assert any(
        "LOCAL PROJECT • NOT PHONE BACKUP" in label.text() for label in center.findChildren(QLabel)
    )
    center.close()


def test_main_window_records_supported_rom_operations_into_automatic_vault_history(
    tmp_path,
    monkeypatch,
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
    project = window.rom_studio.store.create("Automatic main history")
    window.rom_studio.current_project = project
    recorded = []
    failures = []
    monkeypatch.setattr(
        window.backup_center,
        "capture_operation_checkpoint",
        lambda project_id, operation: recorded.append((project_id, operation)) or True,
    )
    monkeypatch.setattr(
        window.backup_center,
        "capture_failure_checkpoint",
        lambda project_id, operation: failures.append((project_id, operation)) or True,
    )
    try:
        window._record_rom_operation("snapshot", object())
        window._record_rom_failure("execute-recipe", "fixture failure")
        app.processEvents()

        assert recorded == [(project.project_id, "snapshot")]
        assert failures == [(project.project_id, "execute-recipe")]
    finally:
        window.companion_center.transport.close()
        window.close()


def test_activity_handoff_reopens_the_exact_project_vault_checkpoint(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(
        None,
        logo,
        tmp_path,
        app_icon_path=logo,
        app_settings=AppSettings(online_intelligence_enabled=False),
    )
    source = tmp_path / "activity-vault.img"
    source.write_bytes(b"activity vault")
    project = window.rom_studio.store.import_original(
        window.rom_studio.store.create("Activity Vault").project_id,
        source,
    )
    window.rom_studio.store.create_working_copy(project.project_id)
    entry = window.backup_center.project_vault.capture(
        project.project_id,
        label="Activity-linked checkpoint",
        reason="Exact Time Machine handoff fixture",
    )
    try:
        window._open_activity_source(
            "time_machine",
            "project-vault-entry",
            f"{project.project_id}.{entry.entry_id}",
        )
        app.processEvents()

        assert window.stack.currentWidget() is window.backup_center
        assert window.backup_center.vault_selector.currentData() == entry.entry_id
        assert "no restore or phone action started" in window.backup_center.vault_result.text()
    finally:
        window.companion_center.transport.close()
        window.close()


def test_project_vault_queues_automatic_history_after_real_rom_studio_completions(
    tmp_path,
    monkeypatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    source = tmp_path / "automatic-history.img"
    source.write_bytes(b"automatic history")
    workspace = tmp_path / "workspace"
    store = RomProjectStore(workspace)
    project = store.import_original(store.create("Automatic history").project_id, source)
    store.create_working_copy(project.project_id)
    center = BackupCenter(workspace)
    queued = []
    monkeypatch.setattr("romverse.ui.backup_center.start_background", queued.append)

    assert center.capture_operation_checkpoint(project.project_id, "working-copy")
    assert center.capture_operation_checkpoint(project.project_id, "snapshot")
    assert len(queued) == 1
    assert len(center._vault_capture_queue) == 1

    queued.pop(0).run()
    app.processEvents()
    assert len(queued) == 1
    queued.pop(0).run()
    app.processEvents()

    entries = center.project_vault.list_entries(project.project_id)
    assert len(entries) == 2
    assert entries[0].parent_entry_id == entries[1].entry_id
    assert {entry.label for entry in entries} == {
        "Protected working baseline",
        "Verified Time Machine baseline",
    }
    assert center.vault_worker is None
    assert center._vault_capture_queue == []
    center.close()
