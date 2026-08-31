from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OriginalArtifact:
    original_name: str
    workspace_path: str
    size_bytes: int
    sha256: str
    imported_at: str


@dataclass(frozen=True, slots=True)
class RomProject:
    schema_version: int
    project_id: str
    name: str
    created_at: str
    updated_at: str
    device_pack_id: str
    original: OriginalArtifact | None = None
    manifest_digest: str = ""


@dataclass(frozen=True, slots=True)
class ArtifactVerification:
    valid: bool
    status: str
    expected_sha256: str = ""
    actual_sha256: str = ""


@dataclass(frozen=True, slots=True)
class WorkingCopy:
    project_id: str
    workspace_path: str
    source_sha256: str
    size_bytes: int
    created_at: str
    current_sha256: str
    schema_version: int = 1
    modified_ns: int = 0
    record_digest: str = ""


@dataclass(frozen=True, slots=True)
class TimeMachineSnapshot:
    snapshot_id: str
    project_id: str
    workspace_path: str
    sha256: str
    size_bytes: int
    created_at: str
    schema_version: int = 1
    modified_ns: int = 0
    record_digest: str = ""


@dataclass(frozen=True, slots=True)
class RollbackPlan:
    project_id: str
    snapshot_id: str
    target_workspace_path: str
    snapshot_sha256: str
    verified: bool
    execution_locked: bool = True


class ProjectError(RuntimeError):
    pass
