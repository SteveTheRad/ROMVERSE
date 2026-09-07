from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from collections.abc import Callable
from contextlib import suppress
from dataclasses import asdict, fields, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from romverse.infrastructure.local_store import (
    atomic_write_json,
    bounded_regular_files,
    ensure_private_directory,
    ensure_private_file,
    read_json_object,
)
from romverse.rom.models import (
    ArtifactVerification,
    OriginalArtifact,
    ProjectError,
    RollbackPlan,
    RomProject,
    TimeMachineSnapshot,
    WorkingCopy,
)

ProgressCallback = Callable[[int, int], None]


class RomProjectStore:
    MANIFEST_NAME = "project.romverse"
    CHUNK_SIZE = 4 * 1024 * 1024
    MAX_RECORD_BYTES = 1024 * 1024
    MAX_SNAPSHOTS = 4096
    MAX_PROJECTS = 4096

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace.resolve()
        self.projects_root = self.workspace / "projects"
        self.originals_root = self.workspace / "original_roms"
        self.working_root = self.workspace / "working_roms"
        self.snapshots_root = self.workspace / "time_machine"

    def create(self, name: str, device_pack_id: str = "") -> RomProject:
        clean_name = name.strip()
        if not clean_name or len(clean_name) > 80:
            raise ProjectError("Project name must contain 1–80 characters")
        project_id = f"{_slug(clean_name)}-{uuid4().hex[:8]}"
        now = datetime.now(UTC).isoformat()
        project = RomProject(2, project_id, clean_name, now, now, device_pack_id)
        self.workspace.mkdir(parents=True, exist_ok=True)
        ensure_private_directory(self.projects_root, boundary=self.workspace)
        directory = self.projects_root / project_id
        if directory.exists():
            raise ProjectError("Generated project identifier already exists")
        ensure_private_directory(directory, boundary=self.workspace)
        return self._save(project)

    def list_projects(self) -> tuple[RomProject, ...]:
        if self.projects_root.is_symlink() or not self.projects_root.is_dir():
            return ()
        projects: list[RomProject] = []
        try:
            entries = tuple(
                sorted(
                    entry.name
                    for entry in os.scandir(self.projects_root)
                    if entry.is_dir(follow_symlinks=False)
                    and re.fullmatch(r"[a-z0-9-]{1,64}", entry.name)
                )[: self.MAX_PROJECTS]
            )
        except OSError:
            return ()
        for project_id in entries:
            manifest = self.projects_root / project_id / self.MANIFEST_NAME
            try:
                projects.append(self._load_manifest(manifest))
            except (OSError, ValueError, TypeError, KeyError, ProjectError):
                continue
        return tuple(sorted(projects, key=lambda item: item.updated_at, reverse=True))

    def get(self, project_id: str) -> RomProject:
        if not re.fullmatch(r"[a-z0-9-]{1,64}", project_id):
            raise ProjectError("Invalid project identifier")
        manifest = self.projects_root / project_id / self.MANIFEST_NAME
        if not manifest.is_file():
            raise ProjectError("Project does not exist")
        try:
            return self._load_manifest(manifest)
        except OSError as exc:
            raise ProjectError("Project manifest is unavailable or unsafe") from exc
        except (ValueError, TypeError, KeyError) as exc:
            raise ProjectError("Project manifest is invalid") from exc

    def associate_device_pack(
        self,
        project_id: str,
        device_pack_id: str,
        *,
        evidence_sha256: str = "",
        reason: str = "",
    ) -> RomProject:
        """Record a local Device Pack association with immutable audit evidence."""

        project = self.get(project_id)
        pack_id = str(device_pack_id).strip()
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,127}", pack_id):
            raise ProjectError("Invalid Device Pack identifier")
        evidence = str(evidence_sha256).casefold().strip()
        if evidence:
            if not re.fullmatch(r"[0-9a-f]{64}", evidence):
                raise ProjectError("Invalid Device Pack association evidence")
            if project.original is None or project.original.sha256 != evidence:
                raise ProjectError("Device Pack evidence does not match the protected original")
        clean_reason = str(reason).strip()
        if len(clean_reason) > 300 or any(ord(char) < 32 for char in clean_reason):
            raise ProjectError("Invalid Device Pack association reason")
        if project.device_pack_id == pack_id:
            return project

        now = datetime.now(UTC).isoformat()
        updated = replace(project, updated_at=now, device_pack_id=pack_id)
        receipt_id = uuid4().hex
        receipt = {
            "format": "romverse.device-pack-association",
            "schema_version": 1,
            "receipt_id": receipt_id,
            "created_at": now,
            "project_id": project.project_id,
            "previous_device_pack_id": project.device_pack_id,
            "device_pack_id": pack_id,
            "evidence_sha256": evidence,
            "reason": clean_reason,
            "scope": "local-project-metadata-only",
            "device_modified": False,
        }
        receipt_root = self.projects_root / project_id / "device-pack-associations"
        receipt_root.mkdir(parents=True, exist_ok=True)
        updated = self._save(updated)
        self._write_json(receipt_root / "latest.romverse", receipt)
        self._write_json(receipt_root / f"association-{receipt_id[:12]}.romverse", receipt)
        return updated

    def delete_project(self, project_id: str) -> None:
        """Delete one project and its derived working data, never the workspace root."""
        self.get(project_id)
        for root in (self.projects_root, self.working_root, self.snapshots_root):
            target = (root / project_id).resolve()
            if target.parent != root.resolve():
                raise ProjectError("Refusing to delete an unsafe project path")
            if target.exists():
                shutil.rmtree(target)

    def import_original(
        self,
        project_id: str,
        source: Path,
        progress: ProgressCallback | None = None,
    ) -> RomProject:
        project = self.get(project_id)
        if project.original is not None:
            raise ProjectError("This project already has an immutable original")
        unresolved_source = source.expanduser()
        if unresolved_source.is_symlink():
            raise ProjectError("Selected original cannot be a symbolic link")
        source = unresolved_source.resolve()
        if not source.is_file():
            raise ProjectError("Selected original is not a regular file")
        before = source.stat()
        size = before.st_size
        ensure_private_directory(self.originals_root, boundary=self.workspace)
        reserve = max(64 * 1024 * 1024, size // 20)
        if shutil.disk_usage(self.originals_root).free < size + reserve:
            raise ProjectError("Insufficient free space for a protected workspace copy")

        temporary = self.originals_root / f".import-{uuid4().hex}.part"
        digest = hashlib.sha256()
        copied = 0
        try:
            with source.open("rb") as input_stream, temporary.open("xb") as output_stream:
                while chunk := input_stream.read(self.CHUNK_SIZE):
                    output_stream.write(chunk)
                    digest.update(chunk)
                    copied += len(chunk)
                    if progress is not None:
                        progress(copied, size)
                output_stream.flush()
                os.fsync(output_stream.fileno())
            after = source.stat()
            if (
                copied != size
                or before.st_size != after.st_size
                or before.st_mtime_ns != after.st_mtime_ns
                or before.st_ino != after.st_ino
            ):
                raise ProjectError("Selected original changed while it was being protected")
            sha256 = digest.hexdigest()
            safe_name = _safe_filename(source.name)
            destination = self.originals_root / f"{sha256[:16]}-{safe_name}"
            if os.path.lexists(destination):
                if destination.is_symlink() or not destination.is_file():
                    raise ProjectError("Existing protected-original target is unsafe")
                existing = _sha256(destination)
                if existing != sha256 or destination.stat().st_size != size:
                    raise ProjectError("Existing content-addressed original failed integrity check")
                temporary.unlink()
            else:
                os.replace(temporary, destination)
            with suppress(OSError):
                destination.chmod(0o444)
        except Exception:
            with suppress(OSError):
                temporary.unlink()
            raise

        artifact = OriginalArtifact(
            original_name=source.name,
            workspace_path=destination.relative_to(self.workspace).as_posix(),
            size_bytes=size,
            sha256=sha256,
            imported_at=datetime.now(UTC).isoformat(),
        )
        updated = replace(project, updated_at=datetime.now(UTC).isoformat(), original=artifact)
        return self._save(updated)

    def verify_original(
        self,
        project_id: str,
        progress: ProgressCallback | None = None,
    ) -> ArtifactVerification:
        project = self.get(project_id)
        if project.original is None:
            return ArtifactVerification(False, "No original has been imported")
        path = self._artifact_path(project.original.workspace_path)
        if not path.is_file():
            return ArtifactVerification(
                False,
                "Protected original is missing",
                project.original.sha256,
            )
        size = path.stat().st_size
        if size != project.original.size_bytes:
            return ArtifactVerification(
                False,
                "Original size changed",
                project.original.sha256,
            )
        actual = _sha256(path, progress)
        return ArtifactVerification(
            actual == project.original.sha256,
            "Integrity verified" if actual == project.original.sha256 else "SHA-256 mismatch",
            project.original.sha256,
            actual,
        )

    def original_path(self, project_id: str) -> Path:
        project = self.get(project_id)
        if project.original is None:
            raise ProjectError("Project has no original artifact")
        return self._artifact_path(project.original.workspace_path)

    def working_copy(self, project_id: str) -> WorkingCopy | None:
        project = self.get(project_id)
        path = self.projects_root / project_id / "working-copy.romverse"
        try:
            payload = read_json_object(
                path,
                boundary=self.workspace,
                maximum_bytes=self.MAX_RECORD_BYTES,
            )
            working_fields = {field.name for field in fields(WorkingCopy)}
            if "format" in payload:
                if (
                    set(payload) != {"format", *working_fields}
                    or payload.pop("format") != "romverse.working-copy"
                ):
                    return None
                record = WorkingCopy(**payload)
            else:
                legacy_fields = working_fields - {"schema_version", "modified_ns", "record_digest"}
                if set(payload) != legacy_fields:
                    return None
                record = WorkingCopy(**payload)
            self._working_artifact(project_id, record.workspace_path, must_exist=True)
        except (OSError, TypeError, ValueError, KeyError, ProjectError):
            return None
        if (
            project.original is None
            or record.project_id != project_id
            or record.source_sha256 != project.original.sha256
            or not self._valid_working_metadata(record)
        ):
            return None
        return record

    def create_working_copy(
        self, project_id: str, progress: ProgressCallback | None = None
    ) -> WorkingCopy:
        project = self.get(project_id)
        if project.original is None:
            raise ProjectError("Import a protected original before creating a working copy")
        verified = self.verify_original(project_id, progress)
        if not verified.valid:
            raise ProjectError(f"Cannot create working copy: {verified.status}")
        source = self.original_path(project_id)
        destination = self.working_root / project_id / "original-baseline.bin"
        ensure_private_directory(destination.parent, boundary=self.workspace)
        if os.path.lexists(destination):
            if destination.is_symlink() or not destination.is_file():
                raise ProjectError("Working-copy target is unsafe")
        else:
            temporary = destination.parent / f".{destination.name}.{uuid4().hex}.part"
            try:
                with source.open("rb") as input_stream, temporary.open("xb") as output_stream:
                    shutil.copyfileobj(input_stream, output_stream, self.CHUNK_SIZE)
                    output_stream.flush()
                    os.fsync(output_stream.fileno())
                os.replace(temporary, destination)
            except Exception:
                with suppress(OSError):
                    temporary.unlink()
                raise
        digest = _sha256(destination, progress)
        if digest != project.original.sha256:
            raise ProjectError("Working copy failed integrity verification")
        now = datetime.now(UTC).isoformat()
        details = destination.stat()
        record = WorkingCopy(
            project_id=project_id,
            workspace_path=destination.relative_to(self.workspace).as_posix(),
            source_sha256=project.original.sha256,
            size_bytes=details.st_size,
            created_at=now,
            current_sha256=digest,
            schema_version=2,
            modified_ns=details.st_mtime_ns,
            record_digest="",
        )
        record = self._seal_working_copy(record)
        self._write_working_copy(record)
        return record

    def create_snapshot(
        self,
        project_id: str,
        progress: ProgressCallback | None = None,
    ) -> TimeMachineSnapshot:
        working = self.working_copy(project_id)
        if working is None:
            raise ProjectError("Create a working copy before taking a snapshot")
        source = self._working_artifact(project_id, working.workspace_path, must_exist=True)
        source_before = source.stat()
        source_size = source_before.st_size
        # Three real byte phases are always performed: source hash, either copy or
        # duplicate verification, and a final hash of the new copy or source. The
        # last unit represents the atomic evidence-record commit, keeping visible
        # 100% unavailable until the receipt genuinely exists.
        total_units = source_size * 3 + 1

        def phase_progress(offset: int) -> ProgressCallback:
            def publish(done: int, _total: int) -> None:
                if progress is not None:
                    progress(offset + min(max(0, done), source_size), total_units)

            return publish

        digest = _sha256(source, phase_progress(0))
        matching = next(
            (
                existing
                for existing in self.list_snapshots(project_id)
                if existing.sha256 == digest and existing.size_bytes == source_size
            ),
            None,
        )
        if matching is not None:
            verification = self.verify_snapshot(matching, phase_progress(source_size))
            if not verification.valid:
                raise ProjectError("Matching Time Machine snapshot failed integrity verification")
            confirmed_digest = _sha256(source, phase_progress(source_size * 2))
            source_after = source.stat()
            if (
                confirmed_digest != digest
                or source_before.st_size != source_after.st_size
                or source_before.st_mtime_ns != source_after.st_mtime_ns
                or source_before.st_ino != source_after.st_ino
            ):
                raise ProjectError(
                    "Working baseline changed while Time Machine verified its snapshot"
                )
            refreshed_working = self._seal_working_copy(
                replace(
                    working,
                    size_bytes=source_after.st_size,
                    current_sha256=digest,
                    schema_version=2,
                    modified_ns=source_after.st_mtime_ns,
                    record_digest="",
                )
            )
            self._write_working_copy(refreshed_working)
            refreshed = next(
                (
                    item
                    for item in self.list_snapshots(project_id)
                    if item.snapshot_id == matching.snapshot_id
                ),
                matching,
            )
            if progress is not None:
                progress(total_units, total_units)
            return refreshed
        reserve = max(64 * 1024 * 1024, source.stat().st_size // 20)
        if shutil.disk_usage(self.workspace).free < source.stat().st_size + reserve:
            raise ProjectError("Insufficient free space for a Time Machine snapshot")
        root = self.snapshots_root / project_id
        ensure_private_directory(root, boundary=self.workspace)
        snapshot_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S") + "-" + uuid4().hex[:6]
        artifact = root / f"{snapshot_id}.bin"
        temporary = root / f".{snapshot_id}.{uuid4().hex}.part"
        artifact_created = False
        try:
            copied = 0
            with source.open("rb") as input_stream, temporary.open("xb") as output_stream:
                while chunk := input_stream.read(self.CHUNK_SIZE):
                    output_stream.write(chunk)
                    copied += len(chunk)
                    if progress is not None:
                        progress(source_size + min(copied, source_size), total_units)
                output_stream.flush()
                os.fsync(output_stream.fileno())
            if copied != source_size:
                raise ProjectError("Time Machine snapshot copy ended before the source")
            ensure_private_file(temporary)
            copied_digest = _sha256(temporary, phase_progress(source_size * 2))
            source_after = source.stat()
            if (
                copied_digest != digest
                or source_before.st_size != source_after.st_size
                or source_before.st_mtime_ns != source_after.st_mtime_ns
                or source_before.st_ino != source_after.st_ino
            ):
                raise ProjectError("Working baseline changed while Time Machine copied it")
            refreshed_working = self._seal_working_copy(
                replace(
                    working,
                    size_bytes=source_after.st_size,
                    current_sha256=digest,
                    schema_version=2,
                    modified_ns=source_after.st_mtime_ns,
                    record_digest="",
                )
            )
            self._write_working_copy(refreshed_working)
            os.replace(temporary, artifact)
            artifact_created = True
            details = artifact.stat()
            record = TimeMachineSnapshot(
                snapshot_id=snapshot_id,
                project_id=project_id,
                workspace_path=artifact.relative_to(self.workspace).as_posix(),
                sha256=copied_digest,
                size_bytes=details.st_size,
                created_at=datetime.now(UTC).isoformat(),
                schema_version=2,
                modified_ns=details.st_mtime_ns,
                record_digest="",
            )
            record = self._seal_snapshot(record)
            self._write_snapshot_record(record)
            if progress is not None:
                progress(total_units, total_units)
            return record
        except Exception:
            with suppress(OSError):
                temporary.unlink()
            if artifact_created:
                with suppress(OSError):
                    artifact.unlink()
            raise

    def list_snapshots(self, project_id: str) -> tuple[TimeMachineSnapshot, ...]:
        self.get(project_id)
        root = self.snapshots_root / project_id
        if root.is_symlink() or not root.is_dir():
            return ()
        try:
            paths = bounded_regular_files(
                root,
                ".romverse",
                boundary=self.workspace,
                maximum_entries=self.MAX_SNAPSHOTS,
            )
        except OSError:
            return ()
        records: list[TimeMachineSnapshot] = []
        for path in paths:
            try:
                record = self._load_snapshot_record(path, project_id)
                if record is not None:
                    records.append(record)
            except (OSError, ValueError, TypeError, ProjectError):
                continue
        return tuple(sorted(records, key=lambda item: item.created_at, reverse=True))

    def verify_snapshot(
        self,
        snapshot: TimeMachineSnapshot,
        progress: ProgressCallback | None = None,
    ) -> ArtifactVerification:
        try:
            if not self._valid_snapshot_metadata(snapshot):
                raise ProjectError("Snapshot record is invalid")
            path = self._snapshot_artifact(snapshot, must_exist=True)
            details = path.stat()
        except (OSError, ProjectError):
            return ArtifactVerification(False, "Snapshot artifact is missing", snapshot.sha256)
        if details.st_size != snapshot.size_bytes or (
            snapshot.schema_version == 2 and details.st_mtime_ns != snapshot.modified_ns
        ):
            return ArtifactVerification(False, "Snapshot metadata changed", snapshot.sha256)
        actual = _sha256(path, progress)
        valid = actual == snapshot.sha256
        if valid and snapshot.schema_version == 1:
            upgraded = replace(
                snapshot,
                schema_version=2,
                modified_ns=details.st_mtime_ns,
                record_digest="",
            )
            try:
                self._write_snapshot_record(self._seal_snapshot(upgraded))
            except (OSError, ProjectError):
                return ArtifactVerification(
                    False,
                    "Snapshot verified but its compatibility upgrade could not be saved",
                    snapshot.sha256,
                    actual,
                )
        return ArtifactVerification(
            valid,
            "Snapshot integrity verified" if valid else "Snapshot SHA-256 mismatch",
            snapshot.sha256,
            actual,
        )

    def plan_rollback(self, project_id: str, snapshot_id: str) -> RollbackPlan:
        working = self.working_copy(project_id)
        snapshot = next(
            (item for item in self.list_snapshots(project_id) if item.snapshot_id == snapshot_id),
            None,
        )
        if working is None or snapshot is None:
            raise ProjectError("Working copy or requested snapshot is missing")
        metadata_ready = False
        if snapshot.schema_version == 2:
            try:
                artifact = self._snapshot_artifact(snapshot, must_exist=True)
                details = artifact.stat()
                metadata_ready = (
                    details.st_size == snapshot.size_bytes
                    and details.st_mtime_ns == snapshot.modified_ns
                )
            except (OSError, ProjectError):
                metadata_ready = False
        return RollbackPlan(
            project_id, snapshot_id, working.workspace_path, snapshot.sha256, metadata_ready
        )

    def restore_snapshot(
        self,
        project_id: str,
        snapshot_id: str,
        approval_digest: str = "",
        progress: ProgressCallback | None = None,
    ) -> RollbackPlan:
        plan = self.plan_rollback(project_id, snapshot_id)
        if not plan.verified:
            raise ProjectError("Rollback blocked: snapshot integrity verification failed")
        if approval_digest != plan.snapshot_sha256:
            raise ProjectError("Rollback approval does not match the snapshot digest")
        working_record = self.working_copy(project_id)
        snapshot_record = next(
            (item for item in self.list_snapshots(project_id) if item.snapshot_id == snapshot_id),
            None,
        )
        if working_record is None or snapshot_record is None:
            raise ProjectError("Rollback evidence changed after approval review")
        working = self._working_artifact(
            project_id,
            working_record.workspace_path,
            must_exist=True,
        )
        snapshot = self._snapshot_artifact(snapshot_record, must_exist=True)
        snapshot_size = snapshot_record.size_bytes
        working_size = working.stat().st_size
        safety_units = working_size * 3 + 1
        copy_offset = snapshot_size + working_size + safety_units
        total_units = copy_offset + snapshot_size * 3 + 1

        def phase_progress(offset: int, phase_size: int) -> ProgressCallback:
            def publish(done: int, _total: int) -> None:
                if progress is not None:
                    progress(offset + min(max(0, done), phase_size), total_units)

            return publish

        if _sha256(snapshot, phase_progress(0, snapshot_size)) != plan.snapshot_sha256:
            raise ProjectError("Rollback blocked: snapshot integrity verification failed")
        before_sha256 = _sha256(
            working,
            phase_progress(snapshot_size, working_size),
        )
        safety_snapshot = self.create_snapshot(
            project_id,
            progress=phase_progress(snapshot_size + working_size, safety_units),
        )
        if safety_snapshot.sha256 != before_sha256:
            raise ProjectError("Working baseline changed before its safety snapshot was sealed")
        temporary = working.with_name(f".{working.name}.{uuid4().hex}.rollback-part")
        try:
            copied = 0
            with snapshot.open("rb") as input_stream, temporary.open("xb") as output_stream:
                while chunk := input_stream.read(self.CHUNK_SIZE):
                    output_stream.write(chunk)
                    copied += len(chunk)
                    if progress is not None:
                        progress(copy_offset + min(copied, snapshot_size), total_units)
                output_stream.flush()
                os.fsync(output_stream.fileno())
            if copied != snapshot_size:
                raise ProjectError("Rollback copy ended before the snapshot")
            if (
                _sha256(
                    temporary,
                    phase_progress(copy_offset + snapshot_size, snapshot_size),
                )
                != plan.snapshot_sha256
            ):
                raise ProjectError("Rollback copy failed integrity verification")
            os.replace(temporary, working)
        except Exception:
            with suppress(OSError):
                temporary.unlink()
            raise
        after_sha256 = _sha256(
            working,
            phase_progress(copy_offset + snapshot_size * 2, snapshot_size),
        )
        if after_sha256 != plan.snapshot_sha256:
            raise ProjectError("Rollback target failed post-restore verification")
        record = self.working_copy(project_id)
        if record is None:
            raise ProjectError("Working copy record disappeared during rollback")
        updated_record = replace(
            record,
            size_bytes=working.stat().st_size,
            current_sha256=after_sha256,
            schema_version=2,
            modified_ns=working.stat().st_mtime_ns,
            record_digest="",
        )
        self._write_working_copy(self._seal_working_copy(updated_record))
        receipt_payload = {
            "format": "romverse.time-machine-restore",
            "schema_version": 2,
            "receipt_id": uuid4().hex,
            "created_at": datetime.now(UTC).isoformat(),
            "project_id": project_id,
            "snapshot_id": snapshot_id,
            "target_workspace_path": plan.target_workspace_path,
            "approval_binding_sha256": plan.snapshot_sha256,
            "pre_restore_snapshot_id": safety_snapshot.snapshot_id,
            "before_sha256": before_sha256,
            "after_sha256": after_sha256,
            "verified": True,
            "scope": "local-working-baseline-only",
            "device_modified": False,
        }
        receipt = {
            **receipt_payload,
            "receipt_digest": _digest(
                {key: value for key, value in receipt_payload.items() if key != "format"}
            ),
        }
        receipt_root = self.projects_root / project_id / "time-machine"
        ensure_private_directory(receipt_root, boundary=self.workspace)
        self._write_json(receipt_root / "latest-restore.romverse", receipt)
        self._write_json(
            receipt_root
            / f"restore-{datetime.now(UTC):%Y%m%dT%H%M%S}-{receipt['receipt_id'][:8]}.romverse",
            receipt,
        )
        if progress is not None:
            progress(total_units, total_units)
        return plan

    def load_latest_restore_receipt(self, project_id: str) -> dict[str, object] | None:
        self.get(project_id)
        path = self.projects_root / project_id / "time-machine" / "latest-restore.romverse"
        try:
            payload = read_json_object(
                path,
                boundary=self.workspace,
                maximum_bytes=self.MAX_RECORD_BYTES,
            )
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return None
        base_fields = {
            "format",
            "schema_version",
            "receipt_id",
            "created_at",
            "project_id",
            "snapshot_id",
            "target_workspace_path",
            "approval_binding_sha256",
            "pre_restore_snapshot_id",
            "before_sha256",
            "after_sha256",
            "verified",
            "scope",
            "device_modified",
        }
        schema_version = payload.get("schema_version")
        expected_fields = base_fields | ({"receipt_digest"} if schema_version == 2 else set())
        snapshots = {item.snapshot_id: item for item in self.list_snapshots(project_id)}
        restored = snapshots.get(str(payload.get("snapshot_id", "")))
        if (
            set(payload) != expected_fields
            or payload.get("format") != "romverse.time-machine-restore"
            or schema_version not in {1, 2}
            or not _hex_value(payload.get("receipt_id"), 32)
            or not _aware_timestamp(payload.get("created_at"))
            or payload.get("project_id") != project_id
            or not _snapshot_id(payload.get("snapshot_id"))
            or not _snapshot_id(payload.get("pre_restore_snapshot_id"))
            or payload.get("target_workspace_path") != self._expected_working_path(project_id)
            or not _sha256_value(payload.get("approval_binding_sha256"))
            or not _sha256_value(payload.get("before_sha256"))
            or not _sha256_value(payload.get("after_sha256"))
            or payload.get("after_sha256") != payload.get("approval_binding_sha256")
            or payload.get("verified") is not True
            or payload.get("scope") != "local-working-baseline-only"
            or payload.get("device_modified") is not False
            or restored is None
            or restored.sha256 != payload.get("after_sha256")
            or (
                schema_version == 2
                and (
                    not _sha256_value(payload.get("receipt_digest"))
                    or payload.get("receipt_digest")
                    != _digest(
                        {
                            key: value
                            for key, value in payload.items()
                            if key not in {"format", "receipt_digest"}
                        }
                    )
                )
            )
        ):
            return None
        return payload

    def _expected_working_path(self, project_id: str) -> str:
        return (
            self.working_root.joinpath(project_id, "original-baseline.bin")
            .relative_to(self.workspace)
            .as_posix()
        )

    def _valid_working_metadata(self, record: WorkingCopy) -> bool:
        values = asdict(record)
        digest = str(values.pop("record_digest"))
        return bool(
            type(record.schema_version) is int
            and record.schema_version in {1, 2}
            and re.fullmatch(r"[a-z0-9-]{1,64}", record.project_id)
            and record.workspace_path == self._expected_working_path(record.project_id)
            and _sha256_value(record.source_sha256)
            and _sha256_value(record.current_sha256)
            and type(record.size_bytes) is int
            and record.size_bytes > 0
            and _aware_timestamp(record.created_at)
            and (
                (
                    record.schema_version == 1
                    and type(record.modified_ns) is int
                    and record.modified_ns == 0
                    and not digest
                )
                or (
                    record.schema_version == 2
                    and type(record.modified_ns) is int
                    and record.modified_ns > 0
                    and _sha256_value(digest)
                    and digest == _digest(values)
                )
            )
        )

    def _seal_working_copy(self, record: WorkingCopy) -> WorkingCopy:
        normalized = replace(record, schema_version=2, record_digest="")
        payload = asdict(normalized)
        payload.pop("record_digest")
        return replace(normalized, record_digest=_digest(payload))

    def _write_working_copy(self, record: WorkingCopy) -> None:
        if record.schema_version != 2 or not self._valid_working_metadata(record):
            raise ProjectError("Working-copy evidence is invalid")
        artifact = self._working_artifact(record.project_id, record.workspace_path, must_exist=True)
        details = artifact.stat()
        if details.st_size != record.size_bytes or details.st_mtime_ns != record.modified_ns:
            raise ProjectError("Working baseline changed before its record was saved")
        atomic_write_json(
            self.projects_root / record.project_id / "working-copy.romverse",
            {"format": "romverse.working-copy", **asdict(record)},
            boundary=self.workspace,
            maximum_bytes=self.MAX_RECORD_BYTES,
        )

    def _working_artifact(
        self,
        project_id: str,
        relative: str,
        *,
        must_exist: bool,
    ) -> Path:
        if relative != self._expected_working_path(project_id):
            raise ProjectError("Working-copy record does not name its isolated baseline")
        return self._contained_path(relative, self.working_root / project_id, must_exist=must_exist)

    def _snapshot_artifact(
        self,
        snapshot: TimeMachineSnapshot,
        *,
        must_exist: bool,
    ) -> Path:
        expected = (
            self.snapshots_root.joinpath(snapshot.project_id, f"{snapshot.snapshot_id}.bin")
            .relative_to(self.workspace)
            .as_posix()
        )
        if snapshot.workspace_path != expected:
            raise ProjectError("Snapshot record does not name its content-addressed artifact")
        return self._contained_path(
            snapshot.workspace_path,
            self.snapshots_root / snapshot.project_id,
            must_exist=must_exist,
        )

    def _contained_path(self, relative: str, boundary: Path, *, must_exist: bool) -> Path:
        candidate = Path(relative)
        if candidate.is_absolute() or ".." in candidate.parts or "\x00" in relative:
            raise ProjectError("Time Machine path is unsafe")
        unresolved = self.workspace / candidate
        current = self.workspace
        for part in candidate.parts:
            current /= part
            if current.is_symlink():
                raise ProjectError("Time Machine paths cannot use symbolic links")
        resolved = unresolved.resolve(strict=must_exist)
        if not resolved.is_relative_to(boundary.resolve()):
            raise ProjectError("Time Machine path escaped its project boundary")
        if must_exist and not resolved.is_file():
            raise ProjectError("Time Machine artifact is unavailable")
        return resolved

    def _valid_snapshot_metadata(self, snapshot: TimeMachineSnapshot) -> bool:
        values = asdict(snapshot)
        digest = str(values.pop("record_digest"))
        return bool(
            type(snapshot.schema_version) is int
            and snapshot.schema_version in {1, 2}
            and _snapshot_id(snapshot.snapshot_id)
            and re.fullmatch(r"[a-z0-9-]{1,64}", snapshot.project_id)
            and _sha256_value(snapshot.sha256)
            and type(snapshot.size_bytes) is int
            and snapshot.size_bytes > 0
            and _aware_timestamp(snapshot.created_at)
            and (
                (
                    snapshot.schema_version == 1
                    and type(snapshot.modified_ns) is int
                    and snapshot.modified_ns == 0
                    and not digest
                )
                or (
                    snapshot.schema_version == 2
                    and type(snapshot.modified_ns) is int
                    and snapshot.modified_ns > 0
                    and _sha256_value(digest)
                    and digest == _digest(values)
                )
            )
        )

    def _load_snapshot_record(
        self,
        path: Path,
        project_id: str,
    ) -> TimeMachineSnapshot | None:
        payload = read_json_object(
            path,
            boundary=self.workspace,
            maximum_bytes=self.MAX_RECORD_BYTES,
        )
        snapshot_fields = {field.name for field in fields(TimeMachineSnapshot)}
        if "format" in payload:
            if (
                set(payload) != {"format", *snapshot_fields}
                or payload.pop("format") != "romverse.time-machine-snapshot"
            ):
                return None
            snapshot = TimeMachineSnapshot(**payload)
        else:
            legacy_fields = snapshot_fields - {"schema_version", "modified_ns", "record_digest"}
            if set(payload) != legacy_fields:
                return None
            snapshot = TimeMachineSnapshot(**payload)
        try:
            artifact = self._snapshot_artifact(snapshot, must_exist=True)
            details = artifact.stat()
        except (OSError, ProjectError):
            return None
        if (
            snapshot.project_id != project_id
            or path.stem != snapshot.snapshot_id
            or not self._valid_snapshot_metadata(snapshot)
            or details.st_size != snapshot.size_bytes
            or (snapshot.schema_version == 2 and details.st_mtime_ns != snapshot.modified_ns)
        ):
            return None
        return snapshot

    def _seal_snapshot(self, snapshot: TimeMachineSnapshot) -> TimeMachineSnapshot:
        normalized = replace(snapshot, schema_version=2, record_digest="")
        payload = asdict(normalized)
        payload.pop("record_digest")
        return replace(normalized, record_digest=_digest(payload))

    def _write_snapshot_record(self, snapshot: TimeMachineSnapshot) -> None:
        if snapshot.schema_version != 2 or not self._valid_snapshot_metadata(snapshot):
            raise ProjectError("Time Machine snapshot record is invalid")
        artifact = self._snapshot_artifact(snapshot, must_exist=True)
        details = artifact.stat()
        if details.st_size != snapshot.size_bytes or details.st_mtime_ns != snapshot.modified_ns:
            raise ProjectError("Time Machine snapshot changed before its record was saved")
        atomic_write_json(
            self.snapshots_root / snapshot.project_id / f"{snapshot.snapshot_id}.romverse",
            {"format": "romverse.time-machine-snapshot", **asdict(snapshot)},
            boundary=self.workspace,
            maximum_bytes=self.MAX_RECORD_BYTES,
        )

    def _write_json(self, path: Path, payload: dict[str, object]) -> None:
        atomic_write_json(
            path,
            payload,
            boundary=self.workspace,
            maximum_bytes=self.MAX_RECORD_BYTES,
        )

    def _save(self, project: RomProject) -> RomProject:
        normalized = replace(project, schema_version=2, manifest_digest="")
        values = asdict(normalized)
        values.pop("manifest_digest")
        normalized = replace(normalized, manifest_digest=_digest(values))
        if not self._valid_project_metadata(normalized):
            raise ProjectError("Project manifest contains invalid metadata")
        directory = self.projects_root / project.project_id
        ensure_private_directory(directory, boundary=self.workspace)
        manifest = directory / self.MANIFEST_NAME
        payload = {"format": "romverse.project", **asdict(normalized)}
        self._write_json(manifest, payload)
        return normalized

    def _load_manifest(self, path: Path) -> RomProject:
        data = read_json_object(
            path,
            boundary=self.workspace,
            maximum_bytes=self.MAX_RECORD_BYTES,
        )
        schema_version = data.get("schema_version")
        project_fields = {field.name for field in fields(RomProject)}
        if schema_version == 1:
            project_fields.remove("manifest_digest")
        if (
            set(data) != {"format", *project_fields}
            or data.pop("format") != "romverse.project"
            or schema_version not in {1, 2}
        ):
            raise ProjectError("Unsupported project manifest")
        original_data = data.pop("original")
        if original_data is not None and (
            not isinstance(original_data, dict)
            or set(original_data) != {field.name for field in fields(OriginalArtifact)}
        ):
            raise ProjectError("Project original metadata is invalid")
        original = OriginalArtifact(**original_data) if original_data else None
        project = RomProject(**data, original=original)
        expected_directory = path.parent.name
        if project.project_id != expected_directory:
            raise ProjectError("Project ID does not match its directory")
        if original is not None:
            self._artifact_path(original.workspace_path)
        if not self._valid_project_metadata(project):
            raise ProjectError("Project manifest metadata is invalid")
        return project

    def _valid_project_metadata(self, project: RomProject) -> bool:
        values = asdict(project)
        digest = str(values.pop("manifest_digest"))
        original = project.original
        return bool(
            type(project.schema_version) is int
            and project.schema_version in {1, 2}
            and re.fullmatch(r"[a-z0-9-]{1,64}", project.project_id)
            and isinstance(project.name, str)
            and 1 <= len(project.name) <= 80
            and project.name == project.name.strip()
            and not any(ord(character) < 32 for character in project.name)
            and _aware_timestamp(project.created_at)
            and _aware_timestamp(project.updated_at)
            and (
                not project.device_pack_id
                or bool(re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,127}", project.device_pack_id))
            )
            and (original is None or _valid_original_metadata(original))
            and (
                (project.schema_version == 1 and not digest)
                or (
                    project.schema_version == 2
                    and _sha256_value(digest)
                    and digest == _digest(values)
                )
            )
        )

    def _artifact_path(self, relative: str) -> Path:
        path = Path(relative)
        if (
            path.is_absolute()
            or len(path.parts) != 2
            or path.parts[0] != self.originals_root.name
            or path.parts[1] in {"", ".", ".."}
            or "\x00" in relative
        ):
            raise ProjectError("Original artifact path escapes the protected store")
        unresolved = self.workspace / path
        current = self.workspace
        for part in path.parts:
            current /= part
            if current.is_symlink():
                raise ProjectError("Protected original paths cannot use symbolic links")
        candidate = unresolved.resolve()
        if not candidate.is_relative_to(self.originals_root.resolve()):
            raise ProjectError("Original artifact path escapes the protected store")
        if candidate.exists() and not candidate.is_file():
            raise ProjectError("Protected original path is not a regular file")
        return candidate


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")[:40]
    return slug or "project"


def _safe_filename(value: str) -> str:
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(value).name).strip("._")
    return (name or "original.bin")[:120]


def _valid_original_metadata(original: OriginalArtifact) -> bool:
    path = Path(original.workspace_path)
    return bool(
        isinstance(original.original_name, str)
        and 1 <= len(original.original_name) <= 255
        and Path(original.original_name).name == original.original_name
        and "\x00" not in original.original_name
        and not path.is_absolute()
        and len(path.parts) == 2
        and path.parts[0] == "original_roms"
        and path.parts[1].startswith(f"{original.sha256[:16]}-")
        and ".." not in path.parts
        and type(original.size_bytes) is int
        and original.size_bytes > 0
        and _sha256_value(original.sha256)
        and _aware_timestamp(original.imported_at)
    )


def _digest(payload: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _sha256_value(value: object) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[0-9a-f]{64}", value))


def _hex_value(value: object, length: int) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(rf"[0-9a-f]{{{length}}}", value))


def _snapshot_id(value: object) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[0-9]{8}T[0-9]{6}-[0-9a-f]{6}", value))


def _aware_timestamp(value: object) -> bool:
    if not isinstance(value, str) or len(value) > 80:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed <= datetime.now(UTC) + timedelta(minutes=5)


def _sha256(path: Path, progress: ProgressCallback | None = None) -> str:
    digest = hashlib.sha256()
    total = path.stat().st_size
    read = 0
    with path.open("rb") as stream:
        while chunk := stream.read(RomProjectStore.CHUNK_SIZE):
            digest.update(chunk)
            read += len(chunk)
            if progress is not None:
                progress(read, total)
    return digest.hexdigest()
