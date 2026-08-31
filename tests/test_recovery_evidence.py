from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from romverse.infrastructure.local_store import LocalStoreError
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore
from romverse.rom.recovery_evidence import RecoveryEvidenceService


def _project(tmp_path: Path):
    source = tmp_path / "firmware.zip"
    source.write_bytes(b"protected firmware")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Recovery", "test.exact")
    project = store.import_original(project.project_id, source)
    return store, project


def test_external_recovery_files_are_hashed_but_not_copied_or_publicly_located(tmp_path):
    store, project = _project(tmp_path)
    backup = tmp_path / "phone-backup.ab"
    stock = tmp_path / "stock-recovery.zip"
    backup.write_bytes(b"independent phone backup")
    stock.write_bytes(b"protected firmware")
    service = RecoveryEvidenceService(store)

    service.register(project.project_id, "external_backup", backup)
    record = service.register(project.project_id, "stock_recovery", stock)
    assessment = service.assess(project.project_id)

    assert assessment.ready
    assert record.external_backup is not None
    assert record.stock_recovery is not None
    assert not record.phone_changed
    public = store.projects_root / project.project_id / service.RECEIPT_NAME
    public_text = public.read_text()
    assert str(tmp_path) not in public_text
    assert "phone-backup.ab" in public_text
    assert not any(path.name == backup.name for path in store.workspace.rglob("*"))
    private = store.projects_root / project.project_id / service.LOCATOR_NAME
    assert json.loads(private.read_text())["locators"]["external_backup"] == str(backup)
    assert private.stat().st_mode & 0o777 == 0o600
    assert stat.S_IMODE(public.stat().st_mode) == 0o600
    assert record.schema_version == 2
    assert len(record.record_digest) == 64


def test_recovery_evidence_detects_changed_artifact_and_verify_fails_closed(tmp_path):
    store, project = _project(tmp_path)
    backup = tmp_path / "phone-backup.ab"
    stock = tmp_path / "stock-recovery.zip"
    backup.write_bytes(b"backup")
    stock.write_bytes(b"protected firmware")
    service = RecoveryEvidenceService(store)
    service.register(project.project_id, "external_backup", backup)
    service.register(project.project_id, "stock_recovery", stock)
    backup.write_bytes(b"changed backup")

    assessment = service.assess(project.project_id)

    assert not assessment.ready
    assert not assessment.external_backup_ready
    with pytest.raises(ProjectError, match="no longer matches"):
        service.verify(project.project_id)


def test_recovery_evidence_rejects_symlinks_and_wrong_roles(tmp_path):
    store, project = _project(tmp_path)
    target = tmp_path / "backup.ab"
    target.write_bytes(b"backup")
    link = tmp_path / "link.ab"
    link.symlink_to(target)
    service = RecoveryEvidenceService(store)

    with pytest.raises(ProjectError, match="symbolic link"):
        service.register(project.project_id, "external_backup", link)
    with pytest.raises(ProjectError, match="Unknown"):
        service.register(project.project_id, "anything", target)


def test_recovery_evidence_rejects_workspace_local_or_wrong_stock_copy(tmp_path):
    store, project = _project(tmp_path)
    service = RecoveryEvidenceService(store)
    workspace_local = store.workspace / "not-independent.ab"
    workspace_local.write_bytes(b"backup")
    wrong_stock = tmp_path / "wrong-stock.zip"
    wrong_stock.write_bytes(b"different build")

    with pytest.raises(ProjectError, match="outside"):
        service.register(project.project_id, "external_backup", workspace_local)
    with pytest.raises(ProjectError, match="protected firmware SHA-256"):
        service.register(project.project_id, "stock_recovery", wrong_stock)


def test_recovery_evidence_is_invalidated_when_project_contract_changes(tmp_path):
    store, project = _project(tmp_path)
    backup = tmp_path / "backup.ab"
    backup.write_bytes(b"backup")
    service = RecoveryEvidenceService(store)
    service.register(project.project_id, "external_backup", backup)
    store.associate_device_pack(project.project_id, "different.exact")

    assert service.load(project.project_id) is None
    assert not service.assess(project.project_id).ready


def test_recovery_evidence_progress_is_monotonic_across_multiple_files(tmp_path):
    store, project = _project(tmp_path)
    backup = tmp_path / "backup.ab"
    stock = tmp_path / "stock-recovery.zip"
    backup.write_bytes(b"backup" * 1_000)
    stock.write_bytes(b"protected firmware")
    service = RecoveryEvidenceService(store)
    service.register(project.project_id, "external_backup", backup)
    service.register(project.project_id, "stock_recovery", stock)
    updates: list[tuple[int, int]] = []

    service.verify(
        project.project_id,
        progress=lambda done, total: updates.append((done, total)),
    )

    total = backup.stat().st_size + stock.stat().st_size
    assert updates == [(backup.stat().st_size, total), (total, total)]


def test_recovery_registration_reports_completion_only_after_evidence_is_saved(tmp_path):
    store, project = _project(tmp_path)
    backup = tmp_path / "backup.ab"
    backup.write_bytes(b"backup")
    service = RecoveryEvidenceService(store)
    receipt = store.projects_root / project.project_id / service.RECEIPT_NAME
    terminal_receipt_state = []

    service.register(
        project.project_id,
        "external_backup",
        backup,
        progress=lambda done, total: (
            terminal_receipt_state.append(receipt.is_file()) if done >= total else None
        ),
    )

    assert terminal_receipt_state == [True]


def test_recovery_record_rejects_extra_oversized_and_symlinked_json(tmp_path):
    store, project = _project(tmp_path)
    backup = tmp_path / "backup.ab"
    backup.write_bytes(b"backup")
    service = RecoveryEvidenceService(store)
    service.register(project.project_id, "external_backup", backup)
    receipt = store.projects_root / project.project_id / service.RECEIPT_NAME
    original = receipt.read_bytes()

    payload = json.loads(original)
    payload["unexpected"] = True
    receipt.write_text(json.dumps(payload), encoding="utf-8")
    assert service.load(project.project_id) is None

    receipt.write_bytes(b"{" + b" " * service.MAX_RECEIPT_BYTES + b"}")
    assert service.load(project.project_id) is None

    outside = tmp_path / "outside-recovery-record.json"
    outside.write_bytes(original)
    receipt.unlink()
    receipt.symlink_to(outside)
    assert service.load(project.project_id) is None
    with pytest.raises(LocalStoreError, match="regular file"):
        service.register(project.project_id, "external_backup", backup)
    assert outside.read_bytes() == original


def test_recovery_private_locator_rejects_hostile_shapes_and_links(tmp_path):
    store, project = _project(tmp_path)
    backup = tmp_path / "backup.ab"
    backup.write_bytes(b"backup")
    service = RecoveryEvidenceService(store)
    service.register(project.project_id, "external_backup", backup)
    locator = store.projects_root / project.project_id / service.LOCATOR_NAME
    original = locator.read_bytes()

    payload = json.loads(original)
    payload["unexpected"] = True
    locator.write_text(json.dumps(payload), encoding="utf-8")
    assert not service.assess(project.project_id).external_backup_ready

    locator.write_bytes(b"{" + b" " * service.MAX_LOCATOR_BYTES + b"}")
    assert not service.assess(project.project_id).external_backup_ready

    outside = tmp_path / "outside-locators.json"
    outside.write_bytes(original)
    locator.unlink()
    locator.symlink_to(outside)
    assert not service.assess(project.project_id).external_backup_ready


def test_recovery_legacy_record_requires_full_verify_before_readiness(tmp_path):
    store, project = _project(tmp_path)
    backup = tmp_path / "backup.ab"
    stock = tmp_path / "stock-recovery.zip"
    backup.write_bytes(b"backup")
    stock.write_bytes(b"protected firmware")
    service = RecoveryEvidenceService(store)
    service.register(project.project_id, "external_backup", backup)
    service.register(project.project_id, "stock_recovery", stock)
    receipt = store.projects_root / project.project_id / service.RECEIPT_NAME
    legacy = json.loads(receipt.read_text())
    legacy["schema_version"] = 1
    legacy.pop("record_digest")
    receipt.write_text(json.dumps(legacy), encoding="utf-8")

    loaded = service.load(project.project_id)
    before = service.assess(project.project_id)

    assert loaded is not None
    assert loaded.schema_version == 1
    assert not before.ready
    assert "fully verified again" in before.evidence[0]

    upgraded = service.verify(project.project_id)

    assert upgraded.schema_version == 2
    assert len(upgraded.record_digest) == 64
    assert service.assess(project.project_id).ready
    assert json.loads(receipt.read_text())["schema_version"] == 2


def test_recovery_locator_cannot_redirect_back_inside_workspace(tmp_path):
    store, project = _project(tmp_path)
    backup = tmp_path / "backup.ab"
    backup.write_bytes(b"backup")
    service = RecoveryEvidenceService(store)
    service.register(project.project_id, "external_backup", backup)
    inside = store.workspace / backup.name
    inside.write_bytes(backup.read_bytes())
    locator = store.projects_root / project.project_id / service.LOCATOR_NAME
    payload = json.loads(locator.read_text())
    payload["locators"]["external_backup"] = str(inside)
    locator.write_text(json.dumps(payload), encoding="utf-8")

    assert not service.assess(project.project_id).external_backup_ready
