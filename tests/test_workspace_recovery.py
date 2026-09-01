from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from romverse.rom.models import ProjectError
from romverse.rom.workspace_recovery import WorkspaceRecoveryService


def _write(path: Path, data: bytes = b"transaction") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def test_recovery_is_shallow_and_removes_only_recognized_transaction_artifacts(
    tmp_path, monkeypatch
) -> None:
    workspace = tmp_path / "workspace"
    project_id = "safe-project"
    outside = tmp_path / "outside"
    outside.mkdir()
    outside_marker = _write(outside / "must-survive.bin", b"preserve")

    original_part = _write(workspace / "original_roms" / ".import-deadbeef.part")
    project_part = _write(workspace / "projects" / project_id / "build-plan.tmp")
    working_part = workspace / "working_roms" / project_id / ".tree-cafebabe"
    _write(working_part / "nested" / "output.bin")
    payload_part = workspace / "working_roms" / project_id / ".partitions-acde1234.part"
    _write(payload_part / "system.img")
    partition_part = (
        workspace
        / "working_roms"
        / project_id
        / "tree"
        / "partition_files"
        / ".system-feedface.part"
    )
    _write(partition_part / "root" / "system" / "build.prop")
    recipe_part = (
        workspace / "time_machine" / project_id / "recipes" / ".20260831T120000-deadbeef.part"
    )
    _write(recipe_part / "snapshot.romverse")
    forge_part = _write(workspace / "builds" / project_id / ".12345678.forge.part")
    verification_part = _write(
        workspace
        / "working_roms"
        / project_id
        / "build-candidates"
        / "candidate-1"
        / ".verification.part"
    )
    linked_part = workspace / "working_roms" / project_id / ".tree-badf00d0"
    linked_part.symlink_to(outside, target_is_directory=True)

    protected_original = _write(workspace / "original_roms" / "verified-firmware.zip", b"firmware")
    completed_tree = _write(
        workspace / "working_roms" / project_id / "tree" / "system" / "build.prop",
        b"ro.romverse=ready\n",
    )
    unknown_part = _write(workspace / "working_roms" / project_id / "tree" / "do-not-search.part")

    def forbidden_recursive_scan(*_args, **_kwargs):
        raise AssertionError("workspace recovery attempted a recursive tree scan")

    monkeypatch.setattr(Path, "rglob", forbidden_recursive_scan)
    report = WorkspaceRecoveryService(workspace).recover(project_id, stale_after_seconds=0)

    expected = {
        original_part,
        project_part,
        working_part,
        payload_part,
        partition_part,
        recipe_part,
        forge_part,
        verification_part,
        linked_part,
    }
    assert set(report.removed_paths) == expected
    assert report.blocked_paths == ()
    assert not report.phone_changed
    assert not report.protected_original_changed
    assert report.execution_authority == "none"
    assert report.bootloader_relock == "never"
    assert protected_original.read_bytes() == b"firmware"
    assert completed_tree.read_bytes() == b"ro.romverse=ready\n"
    assert unknown_part.exists()
    assert outside_marker.read_bytes() == b"preserve"


def test_recovery_honours_stale_age_before_removing_a_recent_transaction(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    candidate = _write(workspace / "original_roms" / ".import-deadbeef.part")
    service = WorkspaceRecoveryService(workspace)

    recent = service.recover(stale_after_seconds=30)
    assert recent.removed_paths == ()
    assert candidate.exists()

    old = time.time() - 60
    os.utime(candidate, (old, old))
    stale = service.recover(stale_after_seconds=30)
    assert stale.removed_paths == (candidate,)
    assert not candidate.exists()


def test_recovery_contains_a_linked_transaction_root_without_touching_its_target(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    project_id = "safe-project"
    outside = tmp_path / "outside-working"
    marker = _write(outside / ".tree-deadbeef" / "keep.bin", b"keep")
    working_root = workspace / "working_roms" / project_id
    working_root.parent.mkdir(parents=True)
    working_root.symlink_to(outside, target_is_directory=True)

    report = WorkspaceRecoveryService(workspace).recover(project_id, stale_after_seconds=0)

    assert working_root in report.blocked_paths
    assert report.removed_paths == ()
    assert marker.read_bytes() == b"keep"


def test_recovery_blocks_an_overfull_transaction_directory_and_invalid_project_id(
    tmp_path, monkeypatch
) -> None:
    workspace = tmp_path / "workspace"
    project_root = workspace / "projects" / "safe-project"
    candidates = tuple(_write(project_root / f"candidate-{index}.tmp") for index in range(3))
    monkeypatch.setattr(WorkspaceRecoveryService, "MAX_DIRECTORY_ENTRIES", 2)
    service = WorkspaceRecoveryService(workspace)

    report = service.recover("safe-project", stale_after_seconds=0)

    assert project_root in report.blocked_paths
    assert all(candidate.exists() for candidate in candidates)
    with pytest.raises(ProjectError, match="invalid project identifier"):
        service.recover("../outside", stale_after_seconds=0)
