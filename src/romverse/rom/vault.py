from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import zipfile
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
from uuid import uuid4

from romverse.infrastructure.local_store import (
    LocalStoreError,
    bounded_regular_files,
    ensure_private_directory,
    exclusive_create_json,
    read_json_object,
)
from romverse.rom.models import ProjectError, TimeMachineSnapshot
from romverse.rom.projects import RomProjectStore


@dataclass(frozen=True, slots=True)
class VaultFile:
    relative_path: str
    object_path: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class VaultEntry:
    schema_version: int
    entry_id: str
    project_id: str
    snapshot_id: str
    parent_entry_id: str
    branch: str
    label: str
    reason: str
    kind: str
    created_at: str
    source_fingerprints: tuple[tuple[str, str], ...]
    context_files: tuple[VaultFile, ...]
    files: tuple[VaultFile, ...]
    tree_bytes: int
    record_digest: str


@dataclass(frozen=True, slots=True)
class VaultVerification:
    valid: bool
    status: str
    verified_files: int
    verified_bytes: int


@dataclass(frozen=True, slots=True)
class VaultComparison:
    left_entry_id: str
    right_entry_id: str
    added: tuple[str, ...]
    removed: tuple[str, ...]
    changed: tuple[str, ...]
    unchanged_count: int
    fingerprint_changes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class VaultBranch:
    schema_version: int
    branch_id: str
    project_id: str
    name: str
    base_entry_id: str
    workspace_path: str
    sha256: str
    size_bytes: int
    created_at: str
    record_digest: str


@dataclass(frozen=True, slots=True)
class VaultStorageReport:
    project_id: str
    snapshot_bytes: int
    tree_object_bytes: int
    branch_bytes: int
    record_bytes: int
    unreferenced_object_bytes: int
    total_bytes: int
    explanation: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RecoveryCapsuleReceipt:
    entry_id: str
    path: str
    sha256: str
    size_bytes: int
    file_count: int
    verified: bool


class ProjectVaultService:
    """Immutable, local project history layered over Time Machine snapshots.

    Vault operations never address an Android transport. They preserve the local
    working baseline, an optional extracted tree, and hash-only project context.
    """

    FORMAT = "romverse.project-vault-entry"
    BRANCH_FORMAT = "romverse.project-vault-branch"
    CAPSULE_FORMAT = "romverse.recovery-capsule"
    RESTORE_FORMAT = "romverse.vault-file-restore"
    SCHEMA_VERSION = 1
    MAX_RECORD_BYTES = 16 * 1024 * 1024
    MAX_FILES = 100_000
    MAX_TREE_BYTES = 512 * 1024**3
    CHUNK_SIZE = 4 * 1024 * 1024
    KINDS = {
        "checkpoint",
        "pre-flash",
        "operation",
        "verified-build",
        "experiment",
        "warning",
        "failure",
    }
    FINGERPRINT_FILES = {
        "project": "project.romverse",
        "firmware-inspection": "inspection.romverse",
        "recipe": "recipe.romverse",
        "partition-map": "payload-manifest.romverse",
        "device-dna": "device-dna.romverse",
        "rom-dna": "rom-dna.romverse",
        "build-plan": "build-plan.romverse",
        "device-build-plan": "device-build-plan.romverse",
        "digital-twin": "device-digital-twin.romverse",
        "simulation-mission": "simulation-mission.romverse",
        "signed-super-assembly": "signed-super-assembly-receipt.romverse",
        "release-forge-plan": "release-forge-plan.romverse",
        "release-certificate": "release-certificate-signature.romverse",
        "release-bundle": "release-bundle-receipt.romverse",
        "first-light": "first-light-report.romverse",
    }

    def __init__(self, store: RomProjectStore) -> None:
        self.store = store
        self.workspace = store.workspace

    def capture(
        self,
        project_id: str,
        *,
        label: str,
        reason: str,
        branch: str = "main",
        kind: str = "checkpoint",
        device_dna_fingerprint: str = "",
    ) -> VaultEntry:
        self.store.get(project_id)
        clean_label = _bounded_text(label, "checkpoint label", 100)
        clean_reason = _bounded_text(reason, "checkpoint reason", 500)
        clean_branch = _branch_name(branch)
        if kind not in self.KINDS:
            raise ProjectError("Unsupported Project Vault checkpoint kind")
        if device_dna_fingerprint and not _sha256_value(device_dna_fingerprint):
            raise ProjectError("Device DNA fingerprint must be a SHA-256 digest")

        root = self._vault_root(project_id, create=True)
        issues = self.entry_issues(project_id)
        if issues:
            raise ProjectError(
                "Project Vault history needs repair before a new checkpoint: " + issues[0]
            )
        snapshot = self.store.create_snapshot(project_id)
        files = self._capture_tree(project_id, root)
        context_files = self._capture_context(project_id, root)
        previous = next(
            (entry for entry in self.list_entries(project_id) if entry.branch == clean_branch),
            None,
        )
        fingerprints = dict(self._project_fingerprints(project_id))
        if device_dna_fingerprint:
            fingerprints["live-device-dna"] = device_dna_fingerprint
        now = datetime.now(UTC)
        entry = VaultEntry(
            schema_version=self.SCHEMA_VERSION,
            entry_id=f"{now:%Y%m%dT%H%M%S}-{uuid4().hex[:8]}",
            project_id=project_id,
            snapshot_id=snapshot.snapshot_id,
            parent_entry_id=previous.entry_id if previous is not None else "",
            branch=clean_branch,
            label=clean_label,
            reason=clean_reason,
            kind=kind,
            created_at=now.isoformat(),
            source_fingerprints=tuple(sorted(fingerprints.items())),
            context_files=context_files,
            files=files,
            tree_bytes=sum(item.size_bytes for item in files),
            record_digest="",
        )
        entry = self._seal_entry(entry)
        entries = root / "entries"
        ensure_private_directory(entries, boundary=self.workspace)
        exclusive_create_json(
            entries / f"{entry.entry_id}.romverse",
            self._entry_payload(entry),
            boundary=self.workspace,
            maximum_bytes=self.MAX_RECORD_BYTES,
        )
        return entry

    def list_entries(self, project_id: str) -> tuple[VaultEntry, ...]:
        self.store.get(project_id)
        root = self._vault_root(project_id) / "entries"
        if root.is_symlink() or not root.is_dir():
            return ()
        try:
            paths = bounded_regular_files(
                root,
                ".romverse",
                boundary=self.workspace,
                maximum_entries=self.MAX_FILES,
            )
        except OSError:
            return ()
        entries: list[VaultEntry] = []
        for path in paths:
            try:
                entry = self._load_entry_path(path, project_id)
            except (OSError, ValueError, TypeError, KeyError, LocalStoreError, ProjectError):
                continue
            entries.append(entry)
        return tuple(sorted(entries, key=lambda item: item.created_at, reverse=True))

    def entry_issues(self, project_id: str) -> tuple[str, ...]:
        """Describe entry paths that cannot participate in trusted project history."""

        self.store.get(project_id)
        root = self._vault_root(project_id) / "entries"
        if not root.exists():
            return ()
        if root.is_symlink() or not root.is_dir():
            return ("entry ledger path is unsafe",)
        issues: list[str] = []
        with os.scandir(root) as scanned:
            entries = tuple(scanned)
        if len(entries) > self.MAX_FILES:
            return ("entry ledger exceeds its file-count boundary",)
        for item in entries:
            if not item.name.endswith(".romverse") or not item.is_file(follow_symlinks=False):
                issues.append(f"unsafe entry path: {item.name[:100]}")
                continue
            try:
                self._load_entry_path(Path(item.path), project_id)
            except (OSError, ValueError, TypeError, KeyError, LocalStoreError, ProjectError):
                issues.append(f"entry integrity failed: {item.name[:100]}")
            if len(issues) >= 20:
                break
        return tuple(issues)

    def load_entry(self, project_id: str, entry_id: str) -> VaultEntry:
        if not _entry_id(entry_id):
            raise ProjectError("Invalid Project Vault entry identifier")
        self.store.get(project_id)
        path = self._vault_root(project_id) / "entries" / f"{entry_id}.romverse"
        try:
            return self._load_entry_path(path, project_id)
        except (OSError, ValueError, TypeError, KeyError, LocalStoreError) as exc:
            raise ProjectError(f"Project Vault entry failed integrity validation: {exc}") from exc

    def verify(self, entry: VaultEntry) -> VaultVerification:
        try:
            current = self.load_entry(entry.project_id, entry.entry_id)
            if current != entry:
                raise ProjectError("Project Vault entry changed after selection")
            snapshot = self._snapshot(entry)
            snapshot_result = self.store.verify_snapshot(snapshot)
            if not snapshot_result.valid:
                return VaultVerification(False, snapshot_result.status, 0, 0)
            verified_bytes = snapshot.size_bytes
            verified_files = 1
            for file in entry.files:
                path = self._object_path(entry.project_id, file)
                actual, size = _hash_stable_file(path, self._vault_root(entry.project_id))
                if size != file.size_bytes or actual != file.sha256:
                    return VaultVerification(
                        False,
                        f"Extracted-tree object changed: {file.relative_path}",
                        verified_files,
                        verified_bytes,
                    )
                verified_files += 1
                verified_bytes += size
            for file in entry.context_files:
                path = self._object_path(entry.project_id, file)
                actual, size = _hash_stable_file(path, self._vault_root(entry.project_id))
                if size != file.size_bytes or actual != file.sha256:
                    return VaultVerification(
                        False,
                        f"Project context object changed: {file.relative_path}",
                        verified_files,
                        verified_bytes,
                    )
                verified_files += 1
                verified_bytes += size
        except (OSError, ValueError, LocalStoreError, ProjectError) as exc:
            return VaultVerification(False, str(exc), 0, 0)
        return VaultVerification(
            True,
            "Baseline snapshot, project fingerprints, and extracted-tree objects verified",
            verified_files,
            verified_bytes,
        )

    def compare(self, left: VaultEntry, right: VaultEntry) -> VaultComparison:
        if left.project_id != right.project_id:
            raise ProjectError("Project Vault comparisons require the same ROM project")
        left_files = {item.relative_path: item for item in left.files}
        right_files = {item.relative_path: item for item in right.files}
        added = tuple(sorted(right_files.keys() - left_files.keys()))
        removed = tuple(sorted(left_files.keys() - right_files.keys()))
        common = left_files.keys() & right_files.keys()
        changed = tuple(
            sorted(path for path in common if left_files[path].sha256 != right_files[path].sha256)
        )
        unchanged = sum(left_files[path].sha256 == right_files[path].sha256 for path in common)
        left_fingerprints = dict(left.source_fingerprints)
        right_fingerprints = dict(right.source_fingerprints)
        roles = left_fingerprints.keys() | right_fingerprints.keys()
        fingerprint_changes = tuple(
            sorted(
                role
                for role in roles
                if left_fingerprints.get(role) != right_fingerprints.get(role)
            )
        )
        return VaultComparison(
            left.entry_id,
            right.entry_id,
            added,
            removed,
            changed,
            unchanged,
            fingerprint_changes,
        )

    def create_branch(self, entry: VaultEntry, name: str) -> VaultBranch:
        clean_name = _bounded_text(name, "branch name", 80)
        verification = self.verify(entry)
        if not verification.valid:
            raise ProjectError(f"Experiment branch blocked: {verification.status}")
        branch_id = f"{_slug(clean_name)}-{uuid4().hex[:8]}"
        root = self._vault_root(entry.project_id, create=True) / "branches" / branch_id
        ensure_private_directory(root, boundary=self.workspace)
        snapshot = self._snapshot(entry)
        source = self.workspace / snapshot.workspace_path
        target = root / "working-baseline.bin"
        _copy_verified(source, target, snapshot.sha256, boundary=self.workspace)
        branch_tree = root / "tree"
        branch_context = root / "context"
        branch_tree.mkdir(mode=0o700)
        branch_context.mkdir(mode=0o700)
        for file in entry.files:
            destination = branch_tree.joinpath(*PurePosixPath(file.relative_path).parts)
            ensure_private_directory(destination.parent, boundary=branch_tree)
            _copy_verified(
                self._object_path(entry.project_id, file),
                destination,
                file.sha256,
                boundary=branch_tree,
            )
        for file in entry.context_files:
            destination = branch_context / file.relative_path
            _copy_verified(
                self._object_path(entry.project_id, file),
                destination,
                file.sha256,
                boundary=branch_context,
            )
        details = target.stat()
        branch = VaultBranch(
            self.SCHEMA_VERSION,
            branch_id,
            entry.project_id,
            clean_name,
            entry.entry_id,
            target.relative_to(self.workspace).as_posix(),
            snapshot.sha256,
            details.st_size,
            datetime.now(UTC).isoformat(),
            "",
        )
        branch = self._seal_branch(branch)
        exclusive_create_json(
            root / "branch.romverse",
            {"format": self.BRANCH_FORMAT, **asdict(branch)},
            boundary=self.workspace,
            maximum_bytes=self.MAX_RECORD_BYTES,
        )
        return branch

    def verify_branch(self, branch: VaultBranch) -> VaultVerification:
        try:
            current = next(
                (
                    item
                    for item in self.list_branches(branch.project_id)
                    if item.branch_id == branch.branch_id
                ),
                None,
            )
            if current != branch:
                raise ProjectError("Experiment branch record changed after selection")
            entry = self.load_entry(branch.project_id, branch.base_entry_id)
            root = self._vault_root(branch.project_id) / "branches" / branch.branch_id
            baseline, size = _hash_stable_file(root / "working-baseline.bin", root)
            if baseline != branch.sha256 or size != branch.size_bytes:
                raise ProjectError("Experiment branch baseline changed")
            verified_files = 1
            verified_bytes = size
            for file in entry.files:
                digest, item_size = _hash_stable_file(
                    root / "tree" / file.relative_path,
                    root,
                )
                if digest != file.sha256 or item_size != file.size_bytes:
                    raise ProjectError(f"Experiment branch file changed: {file.relative_path}")
                verified_files += 1
                verified_bytes += item_size
            for file in entry.context_files:
                digest, item_size = _hash_stable_file(
                    root / "context" / file.relative_path,
                    root,
                )
                if digest != file.sha256 or item_size != file.size_bytes:
                    raise ProjectError(f"Experiment branch context changed: {file.relative_path}")
                verified_files += 1
                verified_bytes += item_size
        except (OSError, ValueError, LocalStoreError, ProjectError) as exc:
            return VaultVerification(False, str(exc), 0, 0)
        return VaultVerification(
            True,
            "Isolated experiment baseline, tree, and project context verified",
            verified_files,
            verified_bytes,
        )

    def list_branches(self, project_id: str) -> tuple[VaultBranch, ...]:
        self.store.get(project_id)
        root = self._vault_root(project_id) / "branches"
        if root.is_symlink() or not root.is_dir():
            return ()
        branches: list[VaultBranch] = []
        for directory in sorted(root.iterdir()):
            if directory.is_symlink() or not directory.is_dir():
                continue
            try:
                payload = read_json_object(
                    directory / "branch.romverse",
                    boundary=self.workspace,
                    maximum_bytes=self.MAX_RECORD_BYTES,
                )
                branch = self._parse_branch(payload, project_id, directory.name)
                path = self.workspace / branch.workspace_path
                details = path.stat()
                if not stat.S_ISREG(details.st_mode) or details.st_size != branch.size_bytes:
                    continue
            except (OSError, ValueError, TypeError, LocalStoreError, ProjectError):
                continue
            branches.append(branch)
        return tuple(sorted(branches, key=lambda item: item.created_at, reverse=True))

    def restore_file(
        self,
        entry: VaultEntry,
        relative_path: str,
        approval_digest: str,
    ) -> dict[str, object]:
        verification = self.verify(entry)
        if not verification.valid:
            raise ProjectError(f"File restore blocked: {verification.status}")
        normalized = _relative_path(relative_path)
        file = next((item for item in entry.files if item.relative_path == normalized), None)
        if file is None:
            raise ProjectError("Selected file is not present in this checkpoint")
        if approval_digest != file.sha256:
            raise ProjectError("File restore approval does not match the selected object")
        tree = self.store.working_root / entry.project_id / "tree"
        if tree.is_symlink():
            raise ProjectError("Working tree cannot traverse a symbolic link")
        ensure_private_directory(tree, boundary=self.workspace)
        target = tree.joinpath(*PurePosixPath(normalized).parts)
        ensure_private_directory(target.parent, boundary=tree)
        before_sha256 = ""
        if target.exists():
            before_sha256, _size = _hash_stable_file(target, tree)
        source = self._object_path(entry.project_id, file)
        _copy_verified(source, target, file.sha256, boundary=tree)
        after_sha256, _size = _hash_stable_file(target, tree)
        if after_sha256 != file.sha256:
            raise ProjectError("Restored file failed its final integrity check")
        receipt = {
            "format": self.RESTORE_FORMAT,
            "schema_version": self.SCHEMA_VERSION,
            "receipt_id": uuid4().hex,
            "created_at": datetime.now(UTC).isoformat(),
            "project_id": entry.project_id,
            "entry_id": entry.entry_id,
            "relative_path": normalized,
            "before_sha256": before_sha256,
            "after_sha256": after_sha256,
            "device_modified": False,
        }
        unsigned = {key: value for key, value in receipt.items() if key != "format"}
        receipt["receipt_digest"] = _digest(unsigned)
        receipts = self._vault_root(entry.project_id, create=True) / "restores"
        ensure_private_directory(receipts, boundary=self.workspace)
        exclusive_create_json(
            receipts / f"file-{receipt['receipt_id']}.romverse",
            receipt,
            boundary=self.workspace,
            maximum_bytes=self.MAX_RECORD_BYTES,
        )
        return receipt

    def restore_state(self, entry: VaultEntry, approval_digest: str) -> dict[str, object]:
        """Restore a whole local project state after digest-bound approval.

        The current baseline, extracted tree, and project context are captured first.
        Protected firmware originals and phone transports are never targets.
        """

        verification = self.verify(entry)
        if not verification.valid:
            raise ProjectError(f"Project-state restore blocked: {verification.status}")
        if approval_digest != entry.record_digest:
            raise ProjectError("Project-state restore approval does not match the checkpoint")
        safety = self.capture(
            entry.project_id,
            label="Automatic pre-restore safety checkpoint",
            reason=f"Preserved before restoring Project Vault entry {entry.entry_id}",
            kind="operation",
        )
        target_snapshot = self._snapshot(entry)
        safety_snapshot = self._snapshot(safety)
        working_root = self.store.working_root / entry.project_id
        tree = working_root / "tree"
        if working_root.is_symlink() or tree.is_symlink():
            raise ProjectError("Project-state restore cannot traverse a symbolic link")
        ensure_private_directory(working_root, boundary=self.workspace)
        temporary_tree = working_root / f".tree.{uuid4().hex}.vault-part"
        previous_tree = working_root / f".tree.{uuid4().hex}.pre-vault"
        temporary_tree.mkdir(mode=0o700)
        baseline_changed = False
        tree_swapped = False
        try:
            for file in entry.files:
                destination = temporary_tree.joinpath(*PurePosixPath(file.relative_path).parts)
                ensure_private_directory(destination.parent, boundary=temporary_tree)
                _copy_verified(
                    self._object_path(entry.project_id, file),
                    destination,
                    file.sha256,
                    boundary=temporary_tree,
                )
            self.store.restore_snapshot(
                entry.project_id,
                target_snapshot.snapshot_id,
                target_snapshot.sha256,
            )
            baseline_changed = True
            if tree.exists():
                os.replace(tree, previous_tree)
            os.replace(temporary_tree, tree)
            tree_swapped = True
            for file in entry.context_files:
                if file.relative_path == "project.romverse":
                    continue
                destination = self.store.projects_root / entry.project_id / file.relative_path
                _copy_verified(
                    self._object_path(entry.project_id, file),
                    destination,
                    file.sha256,
                    boundary=self.store.projects_root / entry.project_id,
                )
            self._remove_absent_context(entry)
            final = self._verify_live_state(entry)
            if not final.valid:
                raise ProjectError(f"Restored project state failed verification: {final.status}")
        except Exception:
            if tree_swapped:
                failed_tree = working_root / f".tree.{uuid4().hex}.failed-vault"
                os.replace(tree, failed_tree)
                if previous_tree.exists():
                    os.replace(previous_tree, tree)
                shutil.rmtree(failed_tree, ignore_errors=True)
            else:
                shutil.rmtree(temporary_tree, ignore_errors=True)
            if baseline_changed:
                self.store.restore_snapshot(
                    entry.project_id,
                    safety_snapshot.snapshot_id,
                    safety_snapshot.sha256,
                )
            self._restore_context_from(safety)
            raise
        shutil.rmtree(previous_tree, ignore_errors=True)
        receipt = {
            "format": "romverse.vault-state-restore",
            "schema_version": self.SCHEMA_VERSION,
            "receipt_id": uuid4().hex,
            "created_at": datetime.now(UTC).isoformat(),
            "project_id": entry.project_id,
            "entry_id": entry.entry_id,
            "safety_entry_id": safety.entry_id,
            "baseline_sha256": target_snapshot.sha256,
            "tree_file_count": len(entry.files),
            "context_file_count": sum(
                item.relative_path != "project.romverse" for item in entry.context_files
            ),
            "verified": True,
            "device_modified": False,
        }
        unsigned = {key: value for key, value in receipt.items() if key != "format"}
        receipt["receipt_digest"] = _digest(unsigned)
        receipts = self._vault_root(entry.project_id, create=True) / "restores"
        ensure_private_directory(receipts, boundary=self.workspace)
        exclusive_create_json(
            receipts / f"state-{receipt['receipt_id']}.romverse",
            receipt,
            boundary=self.workspace,
            maximum_bytes=self.MAX_RECORD_BYTES,
        )
        return receipt

    def export_capsule(self, entry: VaultEntry, destination: Path) -> RecoveryCapsuleReceipt:
        verification = self.verify(entry)
        if not verification.valid:
            raise ProjectError(f"Recovery capsule blocked: {verification.status}")
        destination = destination.expanduser().absolute()
        if destination.exists() or destination.is_symlink():
            raise ProjectError("Recovery capsule destination already exists")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.parent.is_symlink():
            raise ProjectError("Recovery capsule destination cannot be a symbolic link")
        snapshot = self._snapshot(entry)
        baseline = self.workspace / snapshot.workspace_path
        artifacts = [
            {
                "archive_path": "project-baseline.bin",
                "sha256": snapshot.sha256,
                "size_bytes": snapshot.size_bytes,
            }
        ]
        artifacts.extend(
            {
                "archive_path": f"tree/{item.relative_path}",
                "sha256": item.sha256,
                "size_bytes": item.size_bytes,
            }
            for item in entry.files
        )
        artifacts.extend(
            {
                "archive_path": f"context/{item.relative_path}",
                "sha256": item.sha256,
                "size_bytes": item.size_bytes,
            }
            for item in entry.context_files
        )
        manifest = {
            "format": self.CAPSULE_FORMAT,
            "schema_version": self.SCHEMA_VERSION,
            "created_at": datetime.now(UTC).isoformat(),
            "entry": self._entry_payload(entry),
            "artifacts": artifacts,
            "device_modified": False,
        }
        manifest["manifest_digest"] = _digest(
            {key: value for key, value in manifest.items() if key != "format"}
        )
        temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.part")
        try:
            with zipfile.ZipFile(
                temporary,
                "x",
                compression=zipfile.ZIP_DEFLATED,
                compresslevel=6,
                allowZip64=True,
            ) as archive:
                archive.writestr(
                    "capsule.romverse",
                    json.dumps(manifest, ensure_ascii=True, sort_keys=True, indent=2) + "\n",
                )
                archive.write(baseline, "project-baseline.bin")
                for file in entry.files:
                    archive.write(
                        self._object_path(entry.project_id, file),
                        f"tree/{file.relative_path}",
                    )
                for file in entry.context_files:
                    archive.write(
                        self._object_path(entry.project_id, file),
                        f"context/{file.relative_path}",
                    )
            os.replace(temporary, destination)
            destination.chmod(0o600)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        file_count = self._verify_capsule(destination, entry.entry_id)
        digest, size = _hash_stable_file(destination, destination.parent)
        return RecoveryCapsuleReceipt(
            entry.entry_id,
            str(destination),
            digest,
            size,
            file_count,
            True,
        )

    def storage_report(self, project_id: str) -> VaultStorageReport:
        self.store.get(project_id)
        snapshots = self.store.list_snapshots(project_id)
        snapshot_bytes = sum(item.size_bytes for item in snapshots)
        entries = self.list_entries(project_id)
        ledger_issues = self.entry_issues(project_id)
        referenced = {
            item.sha256 for entry in entries for item in (*entry.files, *entry.context_files)
        }
        root = self._vault_root(project_id)
        objects = root / "objects"
        object_bytes = 0
        unreferenced = 0
        if objects.is_dir() and not objects.is_symlink():
            for path in objects.iterdir():
                if path.is_symlink() or not path.is_file():
                    continue
                size = path.stat().st_size
                object_bytes += size
                if not ledger_issues and path.stem not in referenced:
                    unreferenced += size
        branch_total = _regular_tree_bytes(root / "branches", include_suffixes=set())
        branch_records = _regular_tree_bytes(
            root / "branches",
            include_suffixes={".romverse"},
        )
        branch_bytes = max(0, branch_total - branch_records)
        record_bytes = _regular_tree_bytes(root, include_suffixes={".romverse"})
        total = snapshot_bytes + object_bytes + branch_bytes + record_bytes
        return VaultStorageReport(
            project_id,
            snapshot_bytes,
            object_bytes,
            branch_bytes,
            record_bytes,
            unreferenced,
            total,
            (
                "Protected firmware originals are not counted here and are never suggested for removal.",
                "Project snapshots and branch baselines are recoverable history; remove them only after exporting and independently verifying a capsule.",
                (
                    "Cleanup eligibility is unavailable until every rejected Vault entry is repaired."
                    if ledger_issues
                    else "Only unreferenced object bytes are mechanically safe to clean because no valid Vault entry points to them."
                ),
                "Phone backups are separate external archives and are never removed by Project Vault.",
            ),
        )

    def clean_unreferenced_objects(
        self,
        project_id: str,
        approval_project_id: str,
    ) -> dict[str, object]:
        """Remove only objects referenced by no valid entry after exact approval."""

        self.store.get(project_id)
        if approval_project_id != project_id:
            raise ProjectError("Project Vault cleanup approval does not match the project")
        root = self._vault_root(project_id)
        issues = self.entry_issues(project_id)
        if issues:
            raise ProjectError(f"Project Vault cleanup is blocked: {issues[0]}")
        entries = self.list_entries(project_id)
        referenced = {
            item.sha256 for entry in entries for item in (*entry.files, *entry.context_files)
        }
        objects = root / "objects"
        removed_files = 0
        removed_bytes = 0
        if objects.exists():
            if objects.is_symlink() or not objects.is_dir():
                raise ProjectError("Project Vault object storage is unsafe")
            for path in sorted(objects.iterdir()):
                if (
                    path.is_symlink()
                    or not path.is_file()
                    or not re.fullmatch(r"[0-9a-f]{64}\.bin", path.name)
                ):
                    raise ProjectError("Project Vault cleanup found an unsafe object entry")
                if path.stem in referenced:
                    continue
                size = path.stat().st_size
                path.unlink()
                removed_files += 1
                removed_bytes += size
        receipt = {
            "format": "romverse.vault-storage-cleanup",
            "schema_version": self.SCHEMA_VERSION,
            "receipt_id": uuid4().hex,
            "created_at": datetime.now(UTC).isoformat(),
            "project_id": project_id,
            "removed_files": removed_files,
            "removed_bytes": removed_bytes,
            "protected_originals_removed": False,
            "referenced_history_removed": False,
            "phone_backups_removed": False,
            "device_modified": False,
        }
        unsigned = {key: value for key, value in receipt.items() if key != "format"}
        receipt["receipt_digest"] = _digest(unsigned)
        storage_root = root / "storage"
        ensure_private_directory(storage_root, boundary=self.workspace)
        exclusive_create_json(
            storage_root / f"cleanup-{receipt['receipt_id']}.romverse",
            receipt,
            boundary=self.workspace,
            maximum_bytes=self.MAX_RECORD_BYTES,
        )
        return receipt

    def _capture_tree(self, project_id: str, vault_root: Path) -> tuple[VaultFile, ...]:
        tree = self.store.working_root / project_id / "tree"
        if not tree.exists():
            return ()
        if tree.is_symlink() or not tree.is_dir():
            raise ProjectError("Extracted working tree is unsafe")
        objects = vault_root / "objects"
        ensure_private_directory(objects, boundary=self.workspace)
        records: list[VaultFile] = []
        total_bytes = 0
        for current, directories, files in os.walk(tree, followlinks=False):
            current_path = Path(current)
            for name in tuple(directories):
                if (current_path / name).is_symlink():
                    raise ProjectError("Project Vault will not follow a working-tree symbolic link")
            for name in sorted(files):
                path = current_path / name
                details = path.lstat()
                if not stat.S_ISREG(details.st_mode):
                    raise ProjectError("Project Vault accepts regular working-tree files only")
                relative = path.relative_to(tree).as_posix()
                _relative_path(relative)
                digest, size = _hash_stable_file(path, tree)
                total_bytes += size
                if len(records) >= self.MAX_FILES or total_bytes > self.MAX_TREE_BYTES:
                    raise ProjectError("Extracted working tree exceeds the Project Vault boundary")
                target = objects / f"{digest}.bin"
                if target.exists():
                    existing, existing_size = _hash_stable_file(target, vault_root)
                    if existing != digest or existing_size != size:
                        raise ProjectError(
                            "Existing Project Vault object failed integrity validation"
                        )
                else:
                    _copy_verified(path, target, digest, boundary=vault_root)
                records.append(
                    VaultFile(
                        relative,
                        target.relative_to(self.workspace).as_posix(),
                        size,
                        digest,
                    )
                )
        return tuple(sorted(records, key=lambda item: item.relative_path))

    def _capture_context(self, project_id: str, vault_root: Path) -> tuple[VaultFile, ...]:
        project_root = self.store.projects_root / project_id
        objects = vault_root / "objects"
        ensure_private_directory(objects, boundary=self.workspace)
        records: list[VaultFile] = []
        for _role, name in self.FINGERPRINT_FILES.items():
            path = project_root / name
            if not path.exists():
                continue
            digest, size = _hash_stable_file(path, project_root)
            target = objects / f"{digest}.bin"
            if target.exists():
                existing, existing_size = _hash_stable_file(target, vault_root)
                if existing != digest or existing_size != size:
                    raise ProjectError("Existing Project Vault context object failed validation")
            else:
                _copy_verified(path, target, digest, boundary=vault_root)
            records.append(
                VaultFile(
                    name,
                    target.relative_to(self.workspace).as_posix(),
                    size,
                    digest,
                )
            )
        return tuple(sorted(records, key=lambda item: item.relative_path))

    def _project_fingerprints(self, project_id: str) -> tuple[tuple[str, str], ...]:
        project = self.store.get(project_id)
        project_root = self.store.projects_root / project_id
        values: dict[str, str] = {
            "protected-firmware": project.original.sha256 if project.original is not None else ""
        }
        for role, name in self.FINGERPRINT_FILES.items():
            path = project_root / name
            if not path.exists():
                values[role] = ""
                continue
            digest, _size = _hash_stable_file(path, project_root)
            values[role] = digest
        return tuple(sorted(values.items()))

    def _snapshot(self, entry: VaultEntry) -> TimeMachineSnapshot:
        snapshot = next(
            (
                item
                for item in self.store.list_snapshots(entry.project_id)
                if item.snapshot_id == entry.snapshot_id
            ),
            None,
        )
        if snapshot is None:
            raise ProjectError("Checkpoint baseline snapshot is missing")
        return snapshot

    def _verify_live_state(self, entry: VaultEntry) -> VaultVerification:
        working = self.store.working_copy(entry.project_id)
        snapshot = self._snapshot(entry)
        if working is None or working.current_sha256 != snapshot.sha256:
            return VaultVerification(False, "Restored working baseline does not match", 0, 0)
        tree = self.store.working_root / entry.project_id / "tree"
        expected = {item.relative_path: item for item in entry.files}
        observed: dict[str, tuple[str, int]] = {}
        if tree.exists():
            if tree.is_symlink() or not tree.is_dir():
                return VaultVerification(False, "Restored working tree is unsafe", 0, 0)
            for current, directories, files in os.walk(tree, followlinks=False):
                current_path = Path(current)
                if any((current_path / name).is_symlink() for name in directories):
                    return VaultVerification(False, "Restored working tree contains a link", 0, 0)
                for name in files:
                    path = current_path / name
                    if path.is_symlink() or not path.is_file():
                        return VaultVerification(False, "Restored working tree is unsafe", 0, 0)
                    relative = path.relative_to(tree).as_posix()
                    observed[relative] = _hash_stable_file(path, tree)
        if set(observed) != set(expected):
            return VaultVerification(False, "Restored working-tree file set does not match", 0, 0)
        verified_bytes = working.size_bytes
        verified_files = 1
        for relative, file in expected.items():
            digest, size = observed[relative]
            if digest != file.sha256 or size != file.size_bytes:
                return VaultVerification(False, f"Restored file changed: {relative}", 0, 0)
            verified_files += 1
            verified_bytes += size
        project_root = self.store.projects_root / entry.project_id
        expected_context = {item.relative_path: item for item in entry.context_files}
        for name in set(self.FINGERPRINT_FILES.values()) - {"project.romverse"}:
            path = project_root / name
            expected_file = expected_context.get(name)
            if expected_file is None:
                if path.exists():
                    return VaultVerification(
                        False, f"Unexpected restored context file: {name}", 0, 0
                    )
                continue
            digest, size = _hash_stable_file(path, project_root)
            if digest != expected_file.sha256 or size != expected_file.size_bytes:
                return VaultVerification(False, f"Restored context changed: {name}", 0, 0)
            verified_files += 1
            verified_bytes += size
        return VaultVerification(
            True,
            "Whole local project state restored and verified",
            verified_files,
            verified_bytes,
        )

    def _remove_absent_context(self, entry: VaultEntry) -> None:
        expected = {item.relative_path for item in entry.context_files}
        project_root = self.store.projects_root / entry.project_id
        for name in set(self.FINGERPRINT_FILES.values()) - {"project.romverse"} - expected:
            path = project_root / name
            if path.is_symlink():
                raise ProjectError("Project context cannot traverse a symbolic link")
            if path.exists():
                if not path.is_file():
                    raise ProjectError("Project context target is not a regular file")
                path.unlink()

    def _restore_context_from(self, entry: VaultEntry) -> None:
        project_root = self.store.projects_root / entry.project_id
        expected = {item.relative_path: item for item in entry.context_files}
        for name in set(self.FINGERPRINT_FILES.values()) - {"project.romverse"}:
            path = project_root / name
            file = expected.get(name)
            if file is None:
                if path.exists() and not path.is_symlink() and path.is_file():
                    path.unlink()
                continue
            _copy_verified(
                self._object_path(entry.project_id, file),
                path,
                file.sha256,
                boundary=project_root,
            )

    def _object_path(self, project_id: str, file: VaultFile) -> Path:
        expected = self._vault_root(project_id) / "objects" / f"{file.sha256}.bin"
        path = self.workspace / file.object_path
        if path != expected or not path.is_relative_to(self._vault_root(project_id)):
            raise ProjectError("Project Vault object path escapes its protected store")
        if path.is_symlink() or not path.is_file():
            raise ProjectError("Project Vault object is missing")
        return path

    def _vault_root(self, project_id: str, *, create: bool = False) -> Path:
        if not re.fullmatch(r"[a-z0-9-]{1,64}", project_id):
            raise ProjectError("Invalid project identifier")
        root = self.store.snapshots_root / project_id / "vault"
        if create:
            ensure_private_directory(root, boundary=self.workspace)
        return root

    def _entry_payload(self, entry: VaultEntry) -> dict[str, object]:
        return {
            "format": self.FORMAT,
            "schema_version": entry.schema_version,
            "entry_id": entry.entry_id,
            "project_id": entry.project_id,
            "snapshot_id": entry.snapshot_id,
            "parent_entry_id": entry.parent_entry_id,
            "branch": entry.branch,
            "label": entry.label,
            "reason": entry.reason,
            "kind": entry.kind,
            "created_at": entry.created_at,
            "source_fingerprints": [list(item) for item in entry.source_fingerprints],
            "context_files": [asdict(item) for item in entry.context_files],
            "files": [asdict(item) for item in entry.files],
            "tree_bytes": entry.tree_bytes,
            "record_digest": entry.record_digest,
        }

    def _load_entry_path(self, path: Path, project_id: str) -> VaultEntry:
        payload = read_json_object(
            path,
            boundary=self.workspace,
            maximum_bytes=self.MAX_RECORD_BYTES,
        )
        if payload.get("format") != self.FORMAT:
            raise ProjectError("Unsupported Project Vault entry")
        files_raw = payload.get("files")
        context_raw = payload.get("context_files")
        fingerprints_raw = payload.get("source_fingerprints")
        if (
            not isinstance(files_raw, list)
            or not isinstance(context_raw, list)
            or not isinstance(fingerprints_raw, list)
        ):
            raise ProjectError("Project Vault entry lists are invalid")
        if (
            len(files_raw) > self.MAX_FILES
            or len(context_raw) > len(self.FINGERPRINT_FILES)
            or len(fingerprints_raw) > 32
        ):
            raise ProjectError("Project Vault entry exceeds its evidence boundary")
        files = tuple(VaultFile(**item) for item in files_raw if isinstance(item, dict))
        context_files = tuple(VaultFile(**item) for item in context_raw if isinstance(item, dict))
        fingerprints = tuple(
            (str(item[0]), str(item[1]))
            for item in fingerprints_raw
            if isinstance(item, list) and len(item) == 2
        )
        if (
            len(files) != len(files_raw)
            or len(context_files) != len(context_raw)
            or len(fingerprints) != len(fingerprints_raw)
        ):
            raise ProjectError("Project Vault entry evidence is malformed")
        entry = VaultEntry(
            schema_version=payload.get("schema_version"),
            entry_id=payload.get("entry_id"),
            project_id=payload.get("project_id"),
            snapshot_id=payload.get("snapshot_id"),
            parent_entry_id=payload.get("parent_entry_id"),
            branch=payload.get("branch"),
            label=payload.get("label"),
            reason=payload.get("reason"),
            kind=payload.get("kind"),
            created_at=payload.get("created_at"),
            source_fingerprints=fingerprints,
            context_files=context_files,
            files=files,
            tree_bytes=payload.get("tree_bytes"),
            record_digest=payload.get("record_digest"),
        )
        if path.stem != entry.entry_id or not self._valid_entry(entry, project_id):
            raise ProjectError("Project Vault entry metadata is invalid")
        return entry

    def _seal_entry(self, entry: VaultEntry) -> VaultEntry:
        payload = self._entry_payload(entry)
        payload.pop("format")
        payload["record_digest"] = ""
        digest = _digest(payload)
        return replace(entry, record_digest=digest)

    def _valid_entry(self, entry: VaultEntry, project_id: str) -> bool:
        payload = self._entry_payload(entry)
        payload.pop("format")
        stored = str(payload.pop("record_digest", ""))
        payload["record_digest"] = ""
        file_paths = [item.relative_path for item in entry.files]
        return bool(
            entry.schema_version == self.SCHEMA_VERSION
            and entry.project_id == project_id
            and _entry_id(entry.entry_id)
            and (not entry.parent_entry_id or _entry_id(entry.parent_entry_id))
            and re.fullmatch(r"[a-z0-9-]{1,64}", entry.project_id)
            and _snapshot_id(entry.snapshot_id)
            and _branch_name(entry.branch) == entry.branch
            and _valid_text(entry.label, 100)
            and _valid_text(entry.reason, 500)
            and entry.kind in self.KINDS
            and _aware_timestamp(entry.created_at)
            and len(file_paths) == len(set(file_paths))
            and all(self._valid_file(item, project_id) for item in entry.files)
            and len({item.relative_path for item in entry.context_files})
            == len(entry.context_files)
            and all(self._valid_file(item, project_id) for item in entry.context_files)
            and all(
                item.relative_path in set(self.FINGERPRINT_FILES.values())
                for item in entry.context_files
            )
            and entry.tree_bytes == sum(item.size_bytes for item in entry.files)
            and all(
                _valid_role(role) and (not digest or _sha256_value(digest))
                for role, digest in entry.source_fingerprints
            )
            and len({role for role, _digest_value in entry.source_fingerprints})
            == len(entry.source_fingerprints)
            and _sha256_value(stored)
            and stored == _digest(payload)
        )

    def _valid_file(self, file: VaultFile, project_id: str) -> bool:
        expected = f"time_machine/{project_id}/vault/objects/{file.sha256}.bin"
        try:
            normalized = _relative_path(file.relative_path)
        except ProjectError:
            return False
        return bool(
            normalized == file.relative_path
            and file.object_path == expected
            and type(file.size_bytes) is int
            and 0 <= file.size_bytes <= self.MAX_TREE_BYTES
            and _sha256_value(file.sha256)
        )

    def _seal_branch(self, branch: VaultBranch) -> VaultBranch:
        payload = asdict(branch)
        payload["record_digest"] = ""
        return replace(branch, record_digest=_digest(payload))

    def _parse_branch(
        self,
        payload: dict[str, object],
        project_id: str,
        directory_name: str,
    ) -> VaultBranch:
        if set(payload) != {"format", *VaultBranch.__dataclass_fields__}:
            raise ProjectError("Project Vault branch record is invalid")
        if payload.pop("format") != self.BRANCH_FORMAT:
            raise ProjectError("Unsupported Project Vault branch")
        branch = VaultBranch(**payload)
        unsigned = asdict(branch)
        stored = unsigned.pop("record_digest")
        unsigned["record_digest"] = ""
        expected_path = (
            f"time_machine/{project_id}/vault/branches/{branch.branch_id}/working-baseline.bin"
        )
        if not (
            branch.schema_version == self.SCHEMA_VERSION
            and branch.project_id == project_id
            and branch.branch_id == directory_name
            and re.fullmatch(r"[a-z0-9-]{1,64}", branch.branch_id)
            and _valid_text(branch.name, 80)
            and _entry_id(branch.base_entry_id)
            and branch.workspace_path == expected_path
            and _sha256_value(branch.sha256)
            and type(branch.size_bytes) is int
            and branch.size_bytes > 0
            and _aware_timestamp(branch.created_at)
            and _sha256_value(stored)
            and stored == _digest(unsigned)
        ):
            raise ProjectError("Project Vault branch metadata is invalid")
        return branch

    def _verify_capsule(self, path: Path, entry_id: str) -> int:
        try:
            with zipfile.ZipFile(path) as archive:
                infos = archive.infolist()
                if len(infos) > self.MAX_FILES + 2:
                    raise ProjectError("Recovery capsule contains too many files")
                names = [info.filename for info in infos]
                if len(names) != len(set(names)) or "capsule.romverse" not in names:
                    raise ProjectError("Recovery capsule index is invalid")
                raw = archive.read("capsule.romverse")
                if len(raw) > self.MAX_RECORD_BYTES:
                    raise ProjectError("Recovery capsule manifest is too large")
                manifest = json.loads(raw)
                if not isinstance(manifest, dict) or manifest.get("format") != self.CAPSULE_FORMAT:
                    raise ProjectError("Recovery capsule manifest is invalid")
                stored = manifest.get("manifest_digest")
                unsigned = {
                    key: value
                    for key, value in manifest.items()
                    if key not in {"format", "manifest_digest"}
                }
                entry = manifest.get("entry")
                artifacts = manifest.get("artifacts")
                if (
                    not _sha256_value(stored)
                    or stored != _digest(unsigned)
                    or not isinstance(entry, dict)
                    or entry.get("entry_id") != entry_id
                    or not isinstance(artifacts, list)
                ):
                    raise ProjectError("Recovery capsule manifest integrity failed")
                expected_names = {"capsule.romverse"}
                for item in artifacts:
                    if not isinstance(item, dict) or set(item) != {
                        "archive_path",
                        "sha256",
                        "size_bytes",
                    }:
                        raise ProjectError("Recovery capsule artifact record is invalid")
                    archive_path = str(item["archive_path"])
                    _relative_path(archive_path)
                    expected_names.add(archive_path)
                    digest = hashlib.sha256()
                    size = 0
                    with archive.open(archive_path) as stream:
                        while chunk := stream.read(self.CHUNK_SIZE):
                            size += len(chunk)
                            digest.update(chunk)
                    if size != item["size_bytes"] or digest.hexdigest() != item["sha256"]:
                        raise ProjectError("Recovery capsule artifact integrity failed")
                if set(names) != expected_names:
                    raise ProjectError("Recovery capsule contains undeclared files")
        except (OSError, KeyError, TypeError, ValueError, zipfile.BadZipFile) as exc:
            if isinstance(exc, ProjectError):
                raise
            raise ProjectError(f"Recovery capsule verification failed: {exc}") from exc
        return len(expected_names) - 1


def _hash_stable_file(path: Path, boundary: Path) -> tuple[str, int]:
    if path.is_symlink() or not path.is_file():
        raise ProjectError("Project Vault accepts regular local files only")
    resolved_boundary = boundary.resolve()
    resolved = path.resolve()
    if not resolved.is_relative_to(resolved_boundary):
        raise ProjectError("Project Vault file escapes its protected boundary")
    before = path.stat()
    digest = hashlib.sha256()
    read = 0
    with path.open("rb") as stream:
        while chunk := stream.read(ProjectVaultService.CHUNK_SIZE):
            digest.update(chunk)
            read += len(chunk)
    after = path.stat()
    if (
        read != before.st_size
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or before.st_ino != after.st_ino
    ):
        raise ProjectError("Project Vault file changed while it was being verified")
    return digest.hexdigest(), read


def _copy_verified(source: Path, target: Path, expected_sha256: str, *, boundary: Path) -> None:
    if target.exists() and not target.is_symlink():
        actual, _size = _hash_stable_file(target, boundary)
        if actual == expected_sha256:
            return
    if target.is_symlink():
        raise ProjectError("Project Vault destination cannot be a symbolic link")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{uuid4().hex}.part")
    try:
        digest = hashlib.sha256()
        with source.open("rb") as input_stream, temporary.open("xb") as output_stream:
            while chunk := input_stream.read(ProjectVaultService.CHUNK_SIZE):
                output_stream.write(chunk)
                digest.update(chunk)
            output_stream.flush()
            os.fsync(output_stream.fileno())
        if digest.hexdigest() != expected_sha256:
            raise ProjectError("Project Vault copy failed integrity verification")
        temporary.chmod(0o600)
        os.replace(temporary, target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _regular_tree_bytes(root: Path, *, include_suffixes: set[str]) -> int:
    if not root.is_dir() or root.is_symlink():
        return 0
    total = 0
    for current, directories, files in os.walk(root, followlinks=False):
        current_path = Path(current)
        directories[:] = [name for name in directories if not (current_path / name).is_symlink()]
        for name in files:
            path = current_path / name
            if (
                (not include_suffixes or path.suffix in include_suffixes)
                and not path.is_symlink()
                and path.is_file()
            ):
                total += path.stat().st_size
    return total


def _bounded_text(value: str, label: str, maximum: int) -> str:
    clean = " ".join(str(value).replace("\x00", " ").split())
    if not clean or len(clean) > maximum or any(ord(character) < 32 for character in clean):
        raise ProjectError(f"Invalid {label}")
    return clean


def _valid_text(value: object, maximum: int) -> bool:
    return bool(
        isinstance(value, str)
        and 1 <= len(value) <= maximum
        and value == value.strip()
        and not any(ord(character) < 32 for character in value)
    )


def _relative_path(value: str) -> str:
    path = PurePosixPath(str(value))
    if (
        not value
        or len(value) > 4_096
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
        or "\\" in value
        or ":" in value
        or "\x00" in value
    ):
        raise ProjectError("Project Vault relative path is invalid")
    return path.as_posix()


def _branch_name(value: str) -> str:
    clean = " ".join(str(value).replace("\x00", " ").split()).casefold()
    clean = re.sub(r"[^a-z0-9._-]+", "-", clean).strip("-._")
    if not clean or len(clean) > 64:
        raise ProjectError("Invalid Project Vault branch")
    return clean


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")[:40] or "experiment"


def _valid_role(value: str) -> bool:
    return bool(re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", value))


def _entry_id(value: object) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[0-9]{8}T[0-9]{6}-[0-9a-f]{8}", value))


def _snapshot_id(value: object) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[0-9]{8}T[0-9]{6}-[0-9a-f]{6}", value))


def _sha256_value(value: object) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[0-9a-f]{64}", value))


def _aware_timestamp(value: object) -> bool:
    if not isinstance(value, str) or len(value) > 80:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed <= datetime.now(UTC) + timedelta(minutes=5)


def _digest(payload: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()
