from __future__ import annotations

import os
import re
import shutil
import stat
import time
from dataclasses import dataclass
from pathlib import Path

from romverse.rom.models import ProjectError


@dataclass(frozen=True, slots=True)
class WorkspaceRecoveryReport:
    """Bounded cleanup result with no device or protected-source authority."""

    project_id: str
    removed_paths: tuple[Path, ...]
    blocked_paths: tuple[Path, ...]
    phone_changed: bool = False
    protected_original_changed: bool = False
    execution_authority: str = "none"
    bootloader_relock: str = "never"

    @property
    def recovered_count(self) -> int:
        return len(self.removed_paths)


class WorkspaceRecoveryService:
    """Remove only recognized, stale ROMVERSE transaction artifacts.

    Candidate enumeration is intentionally shallow. The completed extracted tree can
    contain hundreds of thousands of files and must never be traversed merely because
    ROMVERSE is recovering from an interrupted operation.
    """

    MAX_DIRECTORY_ENTRIES = 4096
    DEFAULT_STALE_SECONDS = 30
    _PROJECT_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,95}")
    _HEX = r"[0-9a-f]{8,64}"
    _ORIGINAL_PART = re.compile(rf"\.import-{_HEX}\.part")
    _PROJECT_TEMP = re.compile(r"(?:\..+\.)?[^/]+\.(?:tmp|rollback-part)")
    _WORKING_PART = re.compile(
        rf"(?:\.original-baseline\.bin\.{_HEX}\.part|\.tree-{_HEX}|"
        rf"\.partitions-{_HEX}\.part|\.super-unpack-{_HEX}\.part)"
    )
    _PARTITION_PART = re.compile(rf"\.[A-Za-z0-9._-]{{1,80}}-{_HEX}\.part")
    _SNAPSHOT_PART = re.compile(rf"\.[A-Za-z0-9T._-]{{6,96}}(?:\.{_HEX})?\.part")
    _FORGE_PART = re.compile(rf"\.{_HEX}\.forge\.part")
    _VERIFICATION_PART = re.compile(r"\.verification\.part")

    def __init__(self, workspace: Path) -> None:
        unresolved = workspace.expanduser()
        if unresolved.is_symlink():
            raise ProjectError("Workspace recovery refuses a linked workspace root")
        self.workspace = unresolved.resolve()

    def recover(
        self,
        project_id: str = "",
        *,
        stale_after_seconds: int = DEFAULT_STALE_SECONDS,
    ) -> WorkspaceRecoveryReport:
        if project_id and not self._PROJECT_ID.fullmatch(project_id):
            raise ProjectError("Workspace recovery received an invalid project identifier")
        threshold = max(0, int(stale_after_seconds))
        specifications: list[tuple[Path, re.Pattern[str]]] = [
            (self.workspace / "original_roms", self._ORIGINAL_PART),
        ]
        if project_id:
            working = self.workspace / "working_roms" / project_id
            snapshots = self.workspace / "time_machine" / project_id
            specifications.extend(
                (
                    (self.workspace / "projects" / project_id, self._PROJECT_TEMP),
                    (working, self._WORKING_PART),
                    (working / "tree" / "partition_files", self._PARTITION_PART),
                    (snapshots, self._SNAPSHOT_PART),
                    (snapshots / "recipes", self._SNAPSHOT_PART),
                    (snapshots / "debloat", self._SNAPSHOT_PART),
                    (self.workspace / "builds" / project_id, self._FORGE_PART),
                )
            )
            candidates_root = working / "build-candidates"
            if self._safe_directory(candidates_root):
                for candidate in self._bounded_children(candidates_root):
                    if self._safe_directory(candidate):
                        specifications.append((candidate, self._VERIFICATION_PART))

        removed: list[Path] = []
        blocked: list[Path] = []
        seen_directories: set[Path] = set()
        for directory, pattern in specifications:
            if directory in seen_directories:
                continue
            seen_directories.add(directory)
            if not os.path.lexists(directory):
                continue
            if not self._safe_directory(directory):
                blocked.append(directory)
                continue
            try:
                children = self._bounded_children(directory)
            except ProjectError:
                blocked.append(directory)
                continue
            now = time.time()
            for candidate in children:
                if not pattern.fullmatch(candidate.name):
                    continue
                try:
                    details = candidate.lstat()
                    if threshold and now - details.st_mtime < threshold:
                        continue
                    if candidate.parent.resolve(strict=True) != directory.resolve(strict=True):
                        blocked.append(candidate)
                        continue
                    if stat.S_ISLNK(details.st_mode) or stat.S_ISREG(details.st_mode):
                        candidate.unlink()
                    elif stat.S_ISDIR(details.st_mode):
                        shutil.rmtree(candidate)
                    else:
                        blocked.append(candidate)
                        continue
                    removed.append(candidate)
                except OSError:
                    blocked.append(candidate)
        return WorkspaceRecoveryReport(
            project_id,
            tuple(sorted(removed)),
            tuple(sorted(set(blocked))),
        )

    def _safe_directory(self, directory: Path) -> bool:
        try:
            return bool(
                not directory.is_symlink()
                and directory.is_dir()
                and directory.resolve(strict=True).is_relative_to(self.workspace)
            )
        except OSError:
            return False

    def _bounded_children(self, directory: Path) -> tuple[Path, ...]:
        children: list[Path] = []
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    children.append(directory / entry.name)
                    if len(children) > self.MAX_DIRECTORY_ENTRIES:
                        raise ProjectError("Workspace recovery directory exceeds its entry bound")
        except OSError as exc:
            raise ProjectError(
                "Workspace recovery could not enumerate a transaction directory"
            ) from exc
        return tuple(children)
