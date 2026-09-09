import hashlib
import json
import os
import stat
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest

from romverse.infrastructure.local_store import LocalStoreError, windows_private_file_acl
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore


def _assert_private_file(path: Path) -> None:
    if os.name == "nt":
        entries = windows_private_file_acl(path)
        assert len(entries) == 2
        assert {sid for sid, _mask, _inherited in entries} == {
            "S-1-3-4",  # OWNER RIGHTS
            "S-1-5-18",  # LOCAL SYSTEM
        }
        assert all(mask == 0x1F01FF and not inherited for _sid, mask, inherited in entries)
        return
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_create_and_reload_versioned_project(tmp_path):
    store = RomProjectStore(tmp_path)
    project = store.create("My HyperOS Build", "xiaomi.hyperos")
    loaded = store.get(project.project_id)
    assert loaded == project
    assert loaded.device_pack_id == "xiaomi.hyperos"
    manifest = tmp_path / "projects" / project.project_id / "project.romverse"
    data = json.loads(manifest.read_text())
    assert data["format"] == "romverse.project"
    assert data["schema_version"] == 2
    assert len(data["manifest_digest"]) == 64
    _assert_private_file(manifest)


def test_project_manifest_rejects_extra_oversized_and_symlinked_records(tmp_path):
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Hostile manifest")
    manifest = store.projects_root / project.project_id / store.MANIFEST_NAME
    original = manifest.read_bytes()

    payload = json.loads(original)
    payload["unexpected"] = True
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ProjectError, match="Unsupported project manifest"):
        store.get(project.project_id)
    assert store.list_projects() == ()

    manifest.write_bytes(b"{" + b" " * store.MAX_RECORD_BYTES + b"}")
    with pytest.raises(ProjectError, match="unavailable or unsafe"):
        store.get(project.project_id)
    assert store.list_projects() == ()

    outside = tmp_path / "outside-project.json"
    outside.write_bytes(original)
    manifest.unlink()
    manifest.symlink_to(outside)
    with pytest.raises(ProjectError, match="unavailable or unsafe"):
        store.get(project.project_id)
    assert store.list_projects() == ()
    assert outside.read_bytes() == original


def test_project_manifest_rejects_digest_tampering(tmp_path):
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Digest-bound project")
    manifest = store.projects_root / project.project_id / store.MANIFEST_NAME
    payload = json.loads(manifest.read_text())
    payload["name"] = "Tampered but structurally valid"
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ProjectError, match="metadata is invalid"):
        store.get(project.project_id)
    assert store.list_projects() == ()


def test_project_listing_rejects_symlinked_project_directory(tmp_path):
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Linked project")
    directory = store.projects_root / project.project_id
    outside = tmp_path / "outside-project-directory"
    directory.rename(outside)
    directory.symlink_to(outside, target_is_directory=True)

    assert store.list_projects() == ()
    with pytest.raises(ProjectError, match="unavailable or unsafe"):
        store.get(project.project_id)


def test_legacy_project_manifest_is_readable_and_upgrades_on_next_save(tmp_path):
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Legacy manifest")
    manifest = store.projects_root / project.project_id / store.MANIFEST_NAME
    payload = json.loads(manifest.read_text())
    payload["schema_version"] = 1
    payload.pop("manifest_digest")
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    legacy = store.get(project.project_id)

    assert legacy.schema_version == 1
    assert not legacy.manifest_digest

    source = tmp_path / "legacy-source.zip"
    source.write_bytes(b"legacy source")
    upgraded = store.import_original(project.project_id, source)
    stored = json.loads(manifest.read_text())

    assert upgraded.schema_version == 2
    assert len(upgraded.manifest_digest) == 64
    assert stored["schema_version"] == 2
    assert len(stored["manifest_digest"]) == 64


def test_device_pack_association_is_evidence_bound_and_audited(tmp_path):
    source = tmp_path / "firmware.zip"
    source.write_bytes(b"exact firmware source")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Legacy project", "xiaomi.hyperos")
    project = store.import_original(project.project_id, source)

    updated = store.associate_device_pack(
        project.project_id,
        "xiaomi.popsicle.hyperos4.os4.0.0.23",
        evidence_sha256=project.original.sha256,
        reason="Exact protected firmware SHA-256 matched a unique build contract",
    )

    assert updated.device_pack_id == "xiaomi.popsicle.hyperos4.os4.0.0.23"
    assert store.get(project.project_id) == updated
    receipt = json.loads(
        (
            store.projects_root
            / project.project_id
            / "device-pack-associations"
            / "latest.romverse"
        ).read_text()
    )
    assert receipt["previous_device_pack_id"] == "xiaomi.hyperos"
    assert receipt["evidence_sha256"] == project.original.sha256
    assert receipt["device_modified"] is False


def test_device_pack_association_rejects_unsafe_or_wrong_evidence(tmp_path):
    source = tmp_path / "firmware.zip"
    source.write_bytes(b"exact firmware source")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.import_original(store.create("Evidence").project_id, source)

    with pytest.raises(ProjectError, match="identifier"):
        store.associate_device_pack(project.project_id, "../../unsafe")
    with pytest.raises(ProjectError, match="does not match"):
        store.associate_device_pack(
            project.project_id,
            "xiaomi.hyperos",
            evidence_sha256="0" * 64,
        )


def test_import_copies_hashes_and_protects_original_without_touching_source(tmp_path):
    workspace = tmp_path / "workspace"
    source = tmp_path / "firmware.zip"
    content = b"ROMVERSE test firmware\n" * 1000
    source.write_bytes(content)
    original_source_mode = source.stat().st_mode
    progress: list[tuple[int, int]] = []
    store = RomProjectStore(workspace)
    project = store.create("Reference ROM")
    updated = store.import_original(
        project.project_id, source, progress=lambda done, total: progress.append((done, total))
    )

    assert source.read_bytes() == content
    assert source.stat().st_mode == original_source_mode
    assert updated.original is not None
    assert updated.original.sha256 == hashlib.sha256(content).hexdigest()
    protected = workspace / updated.original.workspace_path
    assert protected.read_bytes() == content
    if os.name == "nt":
        _assert_private_file(protected)
    assert not protected.stat().st_mode & stat.S_IWUSR
    assert progress[-1] == (len(content), len(content))
    assert store.verify_original(project.project_id).valid


def test_original_import_fails_closed_when_private_file_enforcement_fails(tmp_path):
    workspace = tmp_path / "workspace"
    source = tmp_path / "firmware.zip"
    content = b"private original required"
    source.write_bytes(content)
    store = RomProjectStore(workspace)
    project = store.create("Private original failure")

    with (
        patch(
            "romverse.rom.projects.ensure_private_file",
            side_effect=LocalStoreError("private ACL unavailable"),
        ),
        pytest.raises(LocalStoreError, match="private ACL unavailable"),
    ):
        store.import_original(project.project_id, source)

    assert source.read_bytes() == content
    assert store.get(project.project_id).original is None
    assert tuple(store.originals_root.iterdir()) == ()


def test_original_import_rejects_source_and_preplanted_target_symlinks(tmp_path):
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Symlink source")
    source = tmp_path / "firmware.zip"
    source.write_bytes(b"protected source")
    source_link = tmp_path / "firmware-link.zip"
    source_link.symlink_to(source)

    with pytest.raises(ProjectError, match="symbolic link"):
        store.import_original(project.project_id, source_link)

    outside = tmp_path / "outside-original.bin"
    outside.write_bytes(b"do not overwrite")
    store.originals_root.mkdir(parents=True)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    planted = store.originals_root / f"{digest[:16]}-{source.name}"
    planted.symlink_to(outside)

    with pytest.raises(ProjectError, match="target is unsafe"):
        store.import_original(project.project_id, source)

    assert outside.read_bytes() == b"do not overwrite"


def test_original_import_rejects_a_source_that_changes_during_copy(tmp_path):
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Changing source")
    source = tmp_path / "changing.zip"
    original = b"stable source bytes"
    source.write_bytes(original)
    changed = False

    def mutate_source(_done: int, _total: int) -> None:
        nonlocal changed
        if not changed:
            source.write_bytes(b"changed while copying")
            changed = True

    with pytest.raises(ProjectError, match="changed while it was being protected"):
        store.import_original(project.project_id, source, progress=mutate_source)

    assert source.read_bytes() != original
    assert store.get(project.project_id).original is None
    assert tuple(store.originals_root.glob("*")) == ()


def test_integrity_verification_detects_changed_original(tmp_path):
    source = tmp_path / "original.img"
    source.write_bytes(b"known original")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Integrity test")
    imported = store.import_original(project.project_id, source)
    protected = store.workspace / imported.original.workspace_path
    protected.chmod(0o644)
    protected.write_bytes(b"tampered data")

    verification = store.verify_original(project.project_id)
    assert not verification.valid
    assert verification.status in {"Original size changed", "SHA-256 mismatch"}


def test_identical_original_is_deduplicated_between_projects(tmp_path):
    source = tmp_path / "same.bin"
    source.write_bytes(b"same content")
    store = RomProjectStore(tmp_path / "workspace")
    first = store.import_original(store.create("First").project_id, source)
    second = store.import_original(store.create("Second").project_id, source)
    assert first.original.workspace_path == second.original.workspace_path
    assert len(list(store.originals_root.glob("*same.bin"))) == 1


def test_existing_original_is_not_reused_when_private_file_enforcement_fails(tmp_path):
    source = tmp_path / "same.bin"
    content = b"same content"
    source.write_bytes(content)
    store = RomProjectStore(tmp_path / "workspace")
    first = store.import_original(store.create("First private").project_id, source)
    second_project = store.create("Second private")
    protected = store.workspace / first.original.workspace_path

    with (
        patch(
            "romverse.rom.projects.ensure_private_file",
            side_effect=LocalStoreError("existing ACL unavailable"),
        ),
        pytest.raises(LocalStoreError, match="existing ACL unavailable"),
    ):
        store.import_original(second_project.project_id, source)

    assert protected.read_bytes() == content
    assert store.get(second_project.project_id).original is None
    assert len(list(store.originals_root.glob("*same.bin"))) == 1


def test_manifest_artifact_cannot_escape_original_store(tmp_path):
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Containment")
    manifest = store.projects_root / project.project_id / store.MANIFEST_NAME
    data = json.loads(manifest.read_text())
    data["original"] = {
        "original_name": "outside",
        "workspace_path": "../outside",
        "size_bytes": 1,
        "sha256": "0" * 64,
        "imported_at": project.created_at,
    }
    manifest.write_text(json.dumps(data))
    with pytest.raises(ProjectError, match="escapes"):
        store.get(project.project_id)


@pytest.mark.parametrize("name", ["", "   ", "x" * 81])
def test_invalid_project_names_are_rejected(tmp_path, name):
    with pytest.raises(ProjectError):
        RomProjectStore(tmp_path).create(name)


def test_second_original_cannot_replace_project_provenance(tmp_path):
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("One original")
    first = tmp_path / "one.bin"
    second = tmp_path / "two.bin"
    first.write_bytes(b"one")
    second.write_bytes(b"two")
    store.import_original(project.project_id, first)
    with pytest.raises(ProjectError, match="already has"):
        store.import_original(project.project_id, second)


def test_project_identifier_validation_blocks_path_traversal(tmp_path):
    with pytest.raises(ProjectError, match="Invalid project identifier"):
        RomProjectStore(tmp_path).get("../outside")


def test_missing_source_is_rejected(tmp_path):
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Missing source")
    with pytest.raises(ProjectError, match="not a regular file"):
        store.import_original(project.project_id, Path(tmp_path / "missing.zip"))


def test_working_copy_and_snapshot_are_verified_and_deduplicated(tmp_path):
    source = tmp_path / "base.img"
    source.write_bytes(b"baseline rom" * 100)
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Time Machine")
    imported = store.import_original(project.project_id, source)

    working = store.create_working_copy(project.project_id)
    assert working.source_sha256 == imported.original.sha256
    assert working.schema_version == 2
    assert len(working.record_digest) == 64
    working_record = store.projects_root / project.project_id / "working-copy.romverse"
    _assert_private_file(working_record)
    assert json.loads(working_record.read_text())["format"] == "romverse.working-copy"
    assert store.working_copy(project.project_id) == working
    snapshot = store.create_snapshot(project.project_id)
    assert snapshot.schema_version == 2
    assert len(snapshot.record_digest) == 64
    snapshot_record = store.snapshots_root / project.project_id / f"{snapshot.snapshot_id}.romverse"
    snapshot_artifact = store.workspace / snapshot.workspace_path
    _assert_private_file(snapshot_record)
    _assert_private_file(snapshot_artifact)
    verify_progress = []
    assert store.verify_snapshot(
        snapshot, progress=lambda done, total: verify_progress.append((done, total))
    ).valid
    assert verify_progress[-1] == (snapshot.size_bytes, snapshot.size_bytes)
    assert store.create_snapshot(project.project_id) == snapshot
    assert len(store.list_snapshots(project.project_id)) == 1
    rollback = store.plan_rollback(project.project_id, snapshot.snapshot_id)
    assert rollback.verified
    assert rollback.execution_locked
    working_path = store.workspace / working.workspace_path
    working_path.write_bytes(b"changed")
    with pytest.raises(ProjectError, match="approval"):
        store.restore_snapshot(project.project_id, snapshot.snapshot_id)
    store.restore_snapshot(project.project_id, snapshot.snapshot_id, snapshot.sha256)
    assert working_path.read_bytes() == b"baseline rom" * 100
    receipt = store.load_latest_restore_receipt(project.project_id)
    assert receipt is not None
    assert receipt["snapshot_id"] == snapshot.snapshot_id
    assert receipt["after_sha256"] == snapshot.sha256
    assert receipt["scope"] == "local-working-baseline-only"
    assert receipt["device_modified"] is False
    assert receipt["schema_version"] == 2
    assert len(str(receipt["receipt_digest"])) == 64
    assert store.working_copy(project.project_id).current_sha256 == snapshot.sha256


def test_snapshot_progress_is_measured_monotonic_and_commits_before_100(
    tmp_path,
    monkeypatch,
):
    source = tmp_path / "measured-snapshot.img"
    source.write_bytes(b"measured baseline" * 500)
    store = RomProjectStore(tmp_path / "workspace")
    project = store.import_original(store.create("Measured snapshot").project_id, source)
    working = store.create_working_copy(project.project_id)
    progress: list[tuple[int, int]] = []
    events: list[str] = []
    write_record = store._write_snapshot_record

    def record_then_publish(snapshot):
        write_record(snapshot)
        events.append("receipt-committed")

    def publish(done: int, total: int) -> None:
        progress.append((done, total))
        if done == total:
            events.append("progress-100")

    monkeypatch.setattr(store, "_write_snapshot_record", record_then_publish)
    snapshot = store.create_snapshot(project.project_id, progress=publish)

    expected_total = working.size_bytes * 3 + 1
    assert progress
    assert {total for _done, total in progress} == {expected_total}
    assert [done for done, _total in progress] == sorted(done for done, _total in progress)
    assert progress[-1] == (expected_total, expected_total)
    assert events == ["receipt-committed", "progress-100"]
    assert (store.workspace / snapshot.workspace_path).read_bytes() == source.read_bytes()

    duplicate_progress: list[tuple[int, int]] = []
    assert (
        store.create_snapshot(
            project.project_id,
            progress=lambda done, total: duplicate_progress.append((done, total)),
        )
        == snapshot
    )
    assert {total for _done, total in duplicate_progress} == {expected_total}
    assert [done for done, _total in duplicate_progress] == sorted(
        done for done, _total in duplicate_progress
    )
    assert duplicate_progress[-1] == (expected_total, expected_total)
    assert len(store.list_snapshots(project.project_id)) == 1


def test_legacy_working_copy_is_readable_and_snapshot_upgrades_it(tmp_path):
    source = tmp_path / "legacy-working.img"
    source.write_bytes(b"legacy working baseline")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.import_original(store.create("Legacy working").project_id, source)
    working = store.create_working_copy(project.project_id)
    record = store.projects_root / project.project_id / "working-copy.romverse"
    payload = json.loads(record.read_text())
    legacy = {
        key: value
        for key, value in payload.items()
        if key
        in {
            "project_id",
            "workspace_path",
            "source_sha256",
            "size_bytes",
            "created_at",
            "current_sha256",
        }
    }
    record.write_text(json.dumps(legacy), encoding="utf-8")

    loaded = store.working_copy(project.project_id)

    assert loaded is not None
    assert loaded.schema_version == 1
    snapshot = store.create_snapshot(project.project_id)
    upgraded = store.working_copy(project.project_id)
    stored = json.loads(record.read_text())

    assert snapshot.schema_version == 2
    assert upgraded is not None
    assert upgraded.schema_version == 2
    assert len(upgraded.record_digest) == 64
    assert stored["format"] == "romverse.working-copy"
    assert stored["schema_version"] == 2
    assert working.workspace_path == upgraded.workspace_path


def test_working_copy_rejects_hostile_record_and_artifact_links(tmp_path):
    source = tmp_path / "working.img"
    source.write_bytes(b"working baseline")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.import_original(store.create("Hostile working").project_id, source)
    working = store.create_working_copy(project.project_id)
    record = store.projects_root / project.project_id / "working-copy.romverse"
    original = record.read_bytes()

    payload = json.loads(original)
    payload["unexpected"] = True
    record.write_text(json.dumps(payload), encoding="utf-8")
    assert store.working_copy(project.project_id) is None

    payload.pop("unexpected")
    payload["record_digest"] = "0" * 64
    record.write_text(json.dumps(payload), encoding="utf-8")
    assert store.working_copy(project.project_id) is None

    record.write_bytes(b"{" + b" " * store.MAX_RECORD_BYTES + b"}")
    assert store.working_copy(project.project_id) is None

    outside = tmp_path / "outside-working.json"
    outside.write_bytes(original)
    record.unlink()
    record.symlink_to(outside)
    assert store.working_copy(project.project_id) is None

    record.unlink()
    record.write_bytes(original)
    artifact = store.workspace / working.workspace_path
    alternate = artifact.with_name("alternate-working.bin")
    alternate.write_bytes(artifact.read_bytes())
    artifact.unlink()
    artifact.symlink_to(alternate.name)
    assert store.working_copy(project.project_id) is None


def _snapshot_fixture(tmp_path):
    source = tmp_path / "snapshot-source.img"
    source.write_bytes(b"snapshot baseline" * 100)
    store = RomProjectStore(tmp_path / "workspace")
    project = store.import_original(store.create("Snapshot fixture").project_id, source)
    store.create_working_copy(project.project_id)
    snapshot = store.create_snapshot(project.project_id)
    return store, project, snapshot


def test_snapshot_records_reject_extra_oversized_and_symlinked_json(tmp_path):
    store, project, snapshot = _snapshot_fixture(tmp_path)
    record = store.snapshots_root / project.project_id / f"{snapshot.snapshot_id}.romverse"
    original = record.read_bytes()

    payload = json.loads(original)
    payload["unexpected"] = True
    record.write_text(json.dumps(payload), encoding="utf-8")
    assert store.list_snapshots(project.project_id) == ()

    record.write_bytes(b"{" + b" " * store.MAX_RECORD_BYTES + b"}")
    assert store.list_snapshots(project.project_id) == ()

    outside = tmp_path / "outside-snapshot.json"
    outside.write_bytes(original)
    record.unlink()
    record.symlink_to(outside)
    assert store.list_snapshots(project.project_id) == ()


def test_snapshot_creation_rejects_redirected_time_machine_directory(tmp_path):
    source = tmp_path / "snapshot-source.img"
    source.write_bytes(b"snapshot baseline")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.import_original(store.create("Redirected snapshots").project_id, source)
    store.create_working_copy(project.project_id)
    outside = tmp_path / "outside-time-machine"
    outside.mkdir()
    store.snapshots_root.symlink_to(outside, target_is_directory=True)

    with pytest.raises(LocalStoreError, match="unsafe or unavailable"):
        store.create_snapshot(project.project_id)

    assert tuple(outside.iterdir()) == ()


def test_legacy_snapshot_is_visible_but_requires_full_verification_to_upgrade(tmp_path):
    store, project, snapshot = _snapshot_fixture(tmp_path)
    record = store.snapshots_root / project.project_id / f"{snapshot.snapshot_id}.romverse"
    payload = json.loads(record.read_text())
    legacy = {
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
    record.write_text(json.dumps(legacy), encoding="utf-8")

    loaded = store.list_snapshots(project.project_id)

    assert len(loaded) == 1
    assert loaded[0].schema_version == 1
    assert not store.plan_rollback(project.project_id, snapshot.snapshot_id).verified
    assert store.verify_snapshot(loaded[0]).valid

    upgraded = store.list_snapshots(project.project_id)
    assert upgraded[0].schema_version == 2
    assert len(upgraded[0].record_digest) == 64
    assert store.plan_rollback(project.project_id, snapshot.snapshot_id).verified


def test_snapshot_artifact_symlink_and_working_target_redirect_fail_closed(tmp_path):
    store, project, snapshot = _snapshot_fixture(tmp_path)
    artifact = store.workspace / snapshot.workspace_path
    alternate = artifact.with_name("alternate.bin")
    alternate.write_bytes(artifact.read_bytes())
    artifact.unlink()
    artifact.symlink_to(alternate.name)

    assert store.list_snapshots(project.project_id) == ()
    assert not store.verify_snapshot(snapshot).valid

    working_record = store.projects_root / project.project_id / "working-copy.romverse"
    original_record = working_record.read_bytes()
    payload = json.loads(original_record)
    redirected = store.working_root / project.project_id / "other.bin"
    redirected.write_bytes(b"snapshot baseline" * 100)
    payload["workspace_path"] = redirected.relative_to(store.workspace).as_posix()
    working_record.write_text(json.dumps(payload), encoding="utf-8")
    assert store.working_copy(project.project_id) is None

    outside_record = tmp_path / "outside-working-copy.json"
    outside_record.write_bytes(original_record)
    working_record.unlink()
    working_record.symlink_to(outside_record)
    assert store.working_copy(project.project_id) is None


def test_rollback_planning_uses_bounded_metadata_and_restore_receipt_is_strict(tmp_path):
    store, project, snapshot = _snapshot_fixture(tmp_path)
    with patch("romverse.rom.projects._sha256", side_effect=AssertionError("unexpected hash")):
        plan = store.plan_rollback(project.project_id, snapshot.snapshot_id)
    assert plan.verified

    working = store.working_copy(project.project_id)
    assert working is not None
    (store.workspace / working.workspace_path).write_bytes(b"changed")
    store.restore_snapshot(project.project_id, snapshot.snapshot_id, snapshot.sha256)
    receipt = store.projects_root / project.project_id / "time-machine" / "latest-restore.romverse"
    original = receipt.read_bytes()

    payload = json.loads(original)
    payload["unexpected"] = True
    receipt.write_text(json.dumps(payload), encoding="utf-8")
    assert store.load_latest_restore_receipt(project.project_id) is None

    receipt.write_bytes(b"{" + b" " * store.MAX_RECORD_BYTES + b"}")
    assert store.load_latest_restore_receipt(project.project_id) is None

    outside = tmp_path / "outside-restore.json"
    outside.write_bytes(original)
    receipt.unlink()
    receipt.symlink_to(outside)
    assert store.load_latest_restore_receipt(project.project_id) is None


def test_restore_rehashes_snapshot_and_binds_pre_restore_safety_copy(tmp_path):
    store, project, snapshot = _snapshot_fixture(tmp_path)
    working = store.working_copy(project.project_id)
    assert working is not None
    working_path = store.workspace / working.workspace_path
    working_path.write_bytes(b"changed working baseline")
    artifact = store.workspace / snapshot.workspace_path
    details = artifact.stat()
    artifact.write_bytes(b"x" * snapshot.size_bytes)
    os.utime(artifact, ns=(details.st_atime_ns, snapshot.modified_ns))

    assert store.plan_rollback(project.project_id, snapshot.snapshot_id).verified
    with pytest.raises(ProjectError, match="snapshot integrity"):
        store.restore_snapshot(project.project_id, snapshot.snapshot_id, snapshot.sha256)
    assert working_path.read_bytes() == b"changed working baseline"

    artifact.write_bytes(b"snapshot baseline" * 100)
    os.utime(artifact, ns=(details.st_atime_ns, snapshot.modified_ns))
    wrong_safety = replace(snapshot, sha256="0" * 64)
    with (
        patch.object(store, "create_snapshot", return_value=wrong_safety),
        pytest.raises(ProjectError, match="safety snapshot"),
    ):
        store.restore_snapshot(project.project_id, snapshot.snapshot_id, snapshot.sha256)
    assert working_path.read_bytes() == b"changed working baseline"


def test_restore_progress_is_measured_and_receipts_commit_before_100(
    tmp_path,
    monkeypatch,
):
    store, project, snapshot = _snapshot_fixture(tmp_path)
    working = store.working_copy(project.project_id)
    assert working is not None
    working_path = store.workspace / working.workspace_path
    working_path.write_bytes(b"changed working baseline with local edits")
    before_size = working_path.stat().st_size
    progress: list[tuple[int, int]] = []
    events: list[str] = []
    write_json = store._write_json

    def record_write(path, payload):
        write_json(path, payload)
        if path.parent.name == "time-machine":
            events.append(path.name)

    def publish(done: int, total: int) -> None:
        progress.append((done, total))
        if done == total:
            events.append("progress-100")

    monkeypatch.setattr(store, "_write_json", record_write)
    store.restore_snapshot(
        project.project_id,
        snapshot.snapshot_id,
        snapshot.sha256,
        progress=publish,
    )

    expected_total = snapshot.size_bytes * 4 + before_size * 4 + 2
    assert progress
    assert {total for _done, total in progress} == {expected_total}
    assert [done for done, _total in progress] == sorted(done for done, _total in progress)
    assert progress[-1] == (expected_total, expected_total)
    assert events[-1] == "progress-100"
    assert events[-3] == "latest-restore.romverse"
    assert events[-2].startswith("restore-")
    assert working_path.read_bytes() == b"snapshot baseline" * 100
