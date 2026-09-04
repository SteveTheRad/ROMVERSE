from __future__ import annotations

import json
import stat
import zipfile

import pytest

from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore
from romverse.rom.vault import ProjectVaultService


def _prepared_vault(tmp_path):
    source = tmp_path / "firmware.zip"
    source.write_bytes(b"protected firmware" * 100)
    store = RomProjectStore(tmp_path / "workspace")
    project = store.import_original(store.create("Project Vault").project_id, source)
    store.create_working_copy(project.project_id)
    tree = store.working_root / project.project_id / "tree"
    (tree / "system").mkdir(parents=True)
    (tree / "system" / "build.prop").write_text("ro.product=test\n", encoding="utf-8")
    (tree / "boot.img").write_bytes(b"boot-v1")
    return store, project, tree, ProjectVaultService(store)


def test_project_vault_captures_compares_and_restores_individual_files(tmp_path) -> None:
    store, project, tree, vault = _prepared_vault(tmp_path)
    (store.projects_root / project.project_id / "first-light-report.romverse").write_text(
        '{"format":"romverse.first-light-report"}\n',
        encoding="utf-8",
    )
    first = vault.capture(
        project.project_id,
        label="Known working baseline",
        reason="Verified before the recipe experiment",
    )
    assert first.branch == "main"
    assert first.parent_entry_id == ""
    assert first.tree_bytes > 0
    assert dict(first.source_fingerprints)["protected-firmware"] == project.original.sha256
    assert dict(first.source_fingerprints)["first-light"]
    assert vault.verify(first).valid

    (tree / "system" / "build.prop").write_text("ro.product=changed\n", encoding="utf-8")
    (tree / "vendor.img").write_bytes(b"vendor")
    second = vault.capture(
        project.project_id,
        label="Recipe experiment",
        reason="Measured comparison after local property work",
        kind="experiment",
    )
    comparison = vault.compare(first, second)
    assert comparison.added == ("vendor.img",)
    assert comparison.removed == ()
    assert comparison.changed == ("system/build.prop",)
    assert second.parent_entry_id == first.entry_id

    original = next(item for item in first.files if item.relative_path == "system/build.prop")
    with pytest.raises(ProjectError, match="approval"):
        vault.restore_file(first, original.relative_path, "0" * 64)
    receipt = vault.restore_file(first, original.relative_path, original.sha256)
    assert (tree / "system" / "build.prop").read_text(encoding="utf-8") == "ro.product=test\n"
    assert receipt["after_sha256"] == original.sha256
    assert receipt["device_modified"] is False


def test_project_vault_creates_isolated_branch_and_verified_recovery_capsule(tmp_path) -> None:
    store, project, _tree, vault = _prepared_vault(tmp_path)
    entry = vault.capture(
        project.project_id,
        label="Pre-flash checkpoint",
        reason="Rollback route captured before a device-changing mission",
        kind="pre-flash",
        device_dna_fingerprint="a" * 64,
    )

    branch = vault.create_branch(entry, "Android Auto experiment")
    branch_path = store.workspace / branch.workspace_path
    assert branch_path.is_file()
    assert stat.S_IMODE(branch_path.stat().st_mode) == 0o600
    assert branch.base_entry_id == entry.entry_id
    assert len(vault.list_branches(project.project_id)) == 1
    assert vault.verify_branch(branch).valid
    assert (
        branch_path.parent / "tree" / "system" / "build.prop"
    ).read_text(encoding="utf-8") == "ro.product=test\n"

    capsule_path = tmp_path / "exports" / "project-recovery.romverse.zip"
    receipt = vault.export_capsule(entry, capsule_path)
    assert receipt.verified
    assert receipt.file_count == len(entry.files) + len(entry.context_files) + 1
    assert stat.S_IMODE(capsule_path.stat().st_mode) == 0o600
    with zipfile.ZipFile(capsule_path) as archive:
        names = set(archive.namelist())
        assert names == {
            "capsule.romverse",
            "project-baseline.bin",
            *(f"tree/{item.relative_path}" for item in entry.files),
            *(f"context/{item.relative_path}" for item in entry.context_files),
        }
        manifest = json.loads(archive.read("capsule.romverse"))
        assert manifest["entry"]["entry_id"] == entry.entry_id
        assert manifest["device_modified"] is False


def test_project_vault_detects_tampering_and_reports_only_unreferenced_cleanup_bytes(
    tmp_path,
) -> None:
    store, project, _tree, vault = _prepared_vault(tmp_path)
    entry = vault.capture(
        project.project_id,
        label="Integrity checkpoint",
        reason="Exercise tamper and storage analysis",
    )
    report = vault.storage_report(project.project_id)
    assert report.snapshot_bytes > 0
    assert report.tree_object_bytes >= entry.tree_bytes
    assert report.unreferenced_object_bytes == 0
    assert "Phone backups are separate" in report.explanation[-1]

    orphan = store.snapshots_root / project.project_id / "vault" / "objects" / f"{'f' * 64}.bin"
    orphan.write_bytes(b"orphan")
    report = vault.storage_report(project.project_id)
    assert report.unreferenced_object_bytes == len(b"orphan")

    with pytest.raises(ProjectError, match="approval"):
        vault.clean_unreferenced_objects(project.project_id, "different-project")
    cleanup = vault.clean_unreferenced_objects(project.project_id, project.project_id)
    assert cleanup["removed_files"] == 1
    assert cleanup["removed_bytes"] == len(b"orphan")
    assert cleanup["referenced_history_removed"] is False
    assert cleanup["phone_backups_removed"] is False
    assert not orphan.exists()

    object_path = store.workspace / entry.files[0].object_path
    object_path.write_bytes(b"tampered")
    verification = vault.verify(entry)
    assert not verification.valid
    assert "changed" in verification.status.casefold()


def test_project_vault_rejects_tampered_records_and_working_tree_links(tmp_path) -> None:
    store, project, tree, vault = _prepared_vault(tmp_path)
    entry = vault.capture(
        project.project_id,
        label="Sealed checkpoint",
        reason="Record validation fixture",
    )
    record = (
        store.snapshots_root
        / project.project_id
        / "vault"
        / "entries"
        / f"{entry.entry_id}.romverse"
    )
    payload = json.loads(record.read_text(encoding="utf-8"))
    payload["reason"] = "substituted"
    record.write_text(json.dumps(payload), encoding="utf-8")
    assert vault.list_entries(project.project_id) == ()
    assert vault.entry_issues(project.project_id)
    with pytest.raises(ProjectError, match="history needs repair"):
        vault.capture(
            project.project_id,
            label="Must not fork corrupt history",
            reason="The invalid parent ledger has to stop capture",
        )

    record.unlink()
    outside = tmp_path / "outside"
    outside.mkdir()
    (tree / "redirect").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ProjectError, match="symbolic link"):
        vault.capture(
            project.project_id,
            label="Unsafe link",
            reason="Must stop before following a redirected tree",
        )


def test_project_vault_restores_complete_state_after_preserving_a_safety_checkpoint(
    tmp_path,
) -> None:
    store, project, tree, vault = _prepared_vault(tmp_path)
    project_root = store.projects_root / project.project_id
    recipe = project_root / "recipe.romverse"
    payload_map = project_root / "payload-manifest.romverse"
    recipe.write_text('{"recipe":"known-working"}\n', encoding="utf-8")
    payload_map.write_text('{"partitions":["boot","system"]}\n', encoding="utf-8")
    entry = vault.capture(
        project.project_id,
        label="Complete known-working state",
        reason="Full-state restore fixture",
    )
    working = store.working_copy(project.project_id)
    assert working is not None
    (store.workspace / working.workspace_path).write_bytes(b"modified baseline")
    (tree / "system" / "build.prop").write_text("ro.product=broken\n", encoding="utf-8")
    (tree / "unexpected.img").write_bytes(b"unexpected")
    recipe.write_text('{"recipe":"broken"}\n', encoding="utf-8")
    payload_map.unlink()
    (project_root / "build-plan.romverse").write_text('{"unexpected":true}\n', encoding="utf-8")

    with pytest.raises(ProjectError, match="approval"):
        vault.restore_state(entry, "0" * 64)
    receipt = vault.restore_state(entry, entry.record_digest)

    assert receipt["verified"] is True
    assert receipt["device_modified"] is False
    assert receipt["safety_entry_id"] != entry.entry_id
    assert (tree / "system" / "build.prop").read_text(encoding="utf-8") == "ro.product=test\n"
    assert not (tree / "unexpected.img").exists()
    assert recipe.read_text(encoding="utf-8") == '{"recipe":"known-working"}\n'
    assert payload_map.read_text(encoding="utf-8") == '{"partitions":["boot","system"]}\n'
    assert not (project_root / "build-plan.romverse").exists()
    target_snapshot = next(
        item
        for item in store.list_snapshots(project.project_id)
        if item.snapshot_id == entry.snapshot_id
    )
    restored_working = store.working_copy(project.project_id)
    assert restored_working is not None
    assert restored_working.current_sha256 == target_snapshot.sha256
    assert len(vault.list_entries(project.project_id)) == 2
