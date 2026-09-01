from __future__ import annotations

import json
import os
from importlib.resources import files
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication, QLabel

from romverse.device.models import AndroidDevice, DeviceState, StorageInfo
from romverse.device_packs.registry import DevicePackRegistry
from romverse.device_packs.validation import DevicePackValidationService
from romverse.rom.projects import RomProjectStore
from romverse.ui.backup_center import BackupCenter, TimeMachineWorker
from romverse.ui.theme import STYLESHEET


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


def test_time_machine_explains_device_atlas_stock_gate_without_inventing_project(
    tmp_path,
) -> None:
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(STYLESHEET)
    center = BackupCenter(tmp_path)
    requested = []
    center.rom_studio_requested.connect(lambda: requested.append(True))

    assert center.open_device_atlas_readiness(_xiaomi_readiness_report())
    app.processEvents()

    assert center.device_atlas_handoff.isVisibleTo(center)
    assert "Stock recovery evidence needed" in center.device_atlas_handoff_title.text()
    assert "Create or import" in center.device_atlas_handoff_detail.text()
    assert "No worker or phone action started" in center.device_atlas_handoff_detail.text()
    assert center.device_atlas_project_button.isVisibleTo(center)
    assert center.snapshot_list.palette().color(QPalette.ColorRole.Base).lightness() < 64
    center.device_atlas_project_button.click()
    assert requested == [True]
    center.close()


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
