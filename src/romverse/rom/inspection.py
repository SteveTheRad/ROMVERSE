from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import struct
import tarfile
import zipfile
from collections.abc import Callable
from contextlib import suppress
from dataclasses import asdict, dataclass, fields, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import BinaryIO
from uuid import uuid4

from romverse.infrastructure.local_store import (
    LocalStoreError,
    atomic_write_json,
    ensure_private_directory,
    ensure_private_file,
    read_json_object,
)
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore

ProgressCallback = Callable[[int, int], None]

_METADATA_SIGNALS = {
    "meta-inf/com/android/metadata",
    "meta-inf/com/google/android/updater-script",
    "android-info.txt",
    "care_map.pb",
    "dynamic_partitions_op_list",
    "apex_info.pb",
}


class ContainerKind(StrEnum):
    ZIP = "zip"
    TAR = "tar"
    ANDROID_SPARSE = "android_sparse"
    ANDROID_BOOT = "android_boot"
    ANDROID_PAYLOAD = "android_payload"
    ANDROID_VBMETA = "android_vbmeta"
    EXT4 = "ext4"
    EROFS = "erofs"
    RAW = "raw_or_unknown"


class FindingSeverity(StrEnum):
    INFORMATION = "information"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class InspectionFinding:
    finding_id: str
    severity: FindingSeverity
    title: str
    detail: str


@dataclass(frozen=True, slots=True)
class RomInspectionReport:
    schema_version: int
    generated_at: str
    source_sha256: str
    source_name: str
    container: ContainerKind
    entry_count: int
    uncompressed_bytes: int
    partition_signals: tuple[str, ...]
    metadata_signals: tuple[str, ...]
    findings: tuple[InspectionFinding, ...]
    complete: bool
    record_digest: str = ""


@dataclass(frozen=True, slots=True)
class WorkingTreeSummary:
    file_count: int
    total_bytes: int
    notable_files: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WorkingTreeIndex:
    """Bounded display index; build authority always comes from a fresh tree scan."""

    schema_version: int
    project_id: str
    source_sha256: str
    generated_at: str
    tree_relative_path: str
    file_count: int
    total_bytes: int
    notable_files: tuple[str, ...]
    record_digest: str


@dataclass(frozen=True, slots=True)
class ExtractionBudget:
    expected_bytes: int
    source_bytes: int
    free_bytes: int
    reserve_bytes: int
    hard_limit_bytes: int
    safe: bool
    reason: str


class RomInspector:
    MAX_ARCHIVE_ENTRIES = 100_000
    MAX_FINDINGS = 250

    def inspect(
        self,
        path: Path,
        expected_sha256: str,
        source_name: str = "",
    ) -> RomInspectionReport:
        with path.open("rb") as stream:
            return self.inspect_stream(stream, expected_sha256, source_name or path.name)

    def inspect_stream(
        self,
        stream: BinaryIO,
        expected_sha256: str,
        source_name: str,
    ) -> RomInspectionReport:
        """Inspect one seekable stream without reopening its directory entry."""

        observed_name = source_name
        kind = self._detect_stream(stream)
        findings: list[InspectionFinding] = []
        entries = 0
        uncompressed = 0
        partitions: set[str] = set()
        metadata: set[str] = set()
        complete = True
        try:
            if kind is ContainerKind.ZIP:
                entries, uncompressed, complete = self._inspect_zip(
                    stream, findings, partitions, metadata
                )
            elif kind is ContainerKind.TAR:
                entries, uncompressed, complete = self._inspect_tar(
                    stream, findings, partitions, metadata
                )
            else:
                self._record_name_signals(observed_name, partitions, metadata)
                self._record_finding(
                    findings,
                    InspectionFinding(
                        "container.read_only",
                        FindingSeverity.INFORMATION,
                        "Binary container identified",
                        "ROMVERSE identified the outer format from file signatures and did not mount or extract it.",
                    ),
                )
        except (OSError, tarfile.TarError, zipfile.BadZipFile, RuntimeError) as exc:
            self._record_finding(
                findings,
                InspectionFinding(
                    "archive.invalid",
                    FindingSeverity.CRITICAL,
                    "Archive structure could not be read safely",
                    f"{type(exc).__name__}: {exc}",
                ),
            )
            complete = False
        if not findings:
            self._record_finding(
                findings,
                InspectionFinding(
                    "structure.clear",
                    FindingSeverity.INFORMATION,
                    "No structural safety warning found",
                    "The bounded metadata inspection found no unsafe paths, links, encryption, or extreme compression signals.",
                ),
            )
        return RomInspectionReport(
            1,
            datetime.now(UTC).isoformat(),
            expected_sha256,
            observed_name,
            kind,
            entries,
            uncompressed,
            tuple(sorted(partitions)),
            tuple(sorted(metadata)),
            tuple(findings),
            complete,
        )

    def _inspect_zip(
        self,
        stream: BinaryIO,
        findings: list[InspectionFinding],
        partitions: set[str],
        metadata: set[str],
    ) -> tuple[int, int, bool]:
        stream.seek(0)
        with zipfile.ZipFile(stream) as archive:
            infos = archive.infolist()
            complete = len(infos) <= self.MAX_ARCHIVE_ENTRIES
            if not complete:
                self._record_finding(findings, self._entry_limit(len(infos)))
            total = 0
            for info in infos[: self.MAX_ARCHIVE_ENTRIES]:
                total += max(0, info.file_size)
                self._record_name_signals(info.filename, partitions, metadata)
                if _unsafe_path(info.filename):
                    self._record_finding(findings, self._unsafe_finding(info.filename))
                mode = info.external_attr >> 16
                if stat.S_ISLNK(mode):
                    self._record_finding(findings, self._link_finding(info.filename))
                elif _unsupported_zip_type(info, mode):
                    self._record_finding(findings, self._special_finding(info.filename))
                if info.flag_bits & 0x1:
                    self._record_finding(
                        findings,
                        InspectionFinding(
                            "archive.encrypted",
                            FindingSeverity.WARNING,
                            "Encrypted archive entry",
                            f"{info.filename} cannot be inspected without a key.",
                        ),
                    )
                if (
                    info.compress_size > 0
                    and info.file_size > 100 * 1024 * 1024
                    and info.file_size / info.compress_size > 1000
                ):
                    self._record_finding(
                        findings,
                        InspectionFinding(
                            "archive.compression_ratio",
                            FindingSeverity.WARNING,
                            "Extreme compression ratio",
                            f"{info.filename} reports a ratio above 1000:1; extraction remains locked.",
                        ),
                    )
            return len(infos), total, complete

    def _inspect_tar(
        self,
        stream: BinaryIO,
        findings: list[InspectionFinding],
        partitions: set[str],
        metadata: set[str],
    ) -> tuple[int, int, bool]:
        count = 0
        total = 0
        complete = True
        stream.seek(0)
        with tarfile.open(fileobj=stream, mode="r:*") as archive:
            for member in archive:
                count += 1
                if count > self.MAX_ARCHIVE_ENTRIES:
                    self._record_finding(findings, self._entry_limit(count))
                    complete = False
                    break
                total += max(0, member.size)
                self._record_name_signals(member.name, partitions, metadata)
                if _unsafe_path(member.name):
                    self._record_finding(findings, self._unsafe_finding(member.name))
                if member.issym() or member.islnk():
                    self._record_finding(findings, self._link_finding(member.name))
                elif not (member.isdir() or member.isfile()):
                    self._record_finding(findings, self._special_finding(member.name))
        return count, total, complete

    @staticmethod
    def _detect_stream(stream: BinaryIO) -> ContainerKind:
        stream.seek(0)
        header = stream.read(4096)
        if header.startswith(b"PK\x03\x04") or header.startswith(b"PK\x05\x06"):
            return ContainerKind.ZIP
        if header.startswith(b"ANDROID!"):
            return ContainerKind.ANDROID_BOOT
        if header.startswith(b"CrAU"):
            return ContainerKind.ANDROID_PAYLOAD
        if header.startswith(b"AVB0"):
            return ContainerKind.ANDROID_VBMETA
        if len(header) >= 4 and struct.unpack_from("<I", header)[0] == 0xED26FF3A:
            return ContainerKind.ANDROID_SPARSE
        if len(header) >= 1082 and header[1080:1082] == b"\x53\xef":
            return ContainerKind.EXT4
        if len(header) >= 1028 and struct.unpack_from("<I", header, 1024)[0] == 0xE0F5E1E2:
            return ContainerKind.EROFS
        stream.seek(0)
        try:
            with tarfile.open(fileobj=stream, mode="r:*"):
                return ContainerKind.TAR
        except (OSError, tarfile.TarError):
            return ContainerKind.RAW
        finally:
            stream.seek(0)

    @staticmethod
    def _record_name_signals(
        name: str,
        partitions: set[str],
        metadata: set[str],
    ) -> None:
        normalized = name.replace("\\", "/").lower()
        base = PurePosixPath(normalized).name
        partition_names = {
            "boot.img": "boot",
            "init_boot.img": "init_boot",
            "vendor_boot.img": "vendor_boot",
            "recovery.img": "recovery",
            "super.img": "super",
            "system.img": "system",
            "system_ext.img": "system_ext",
            "product.img": "product",
            "vendor.img": "vendor",
            "odm.img": "odm",
            "vbmeta.img": "vbmeta",
            "dtbo.img": "dtbo",
            "payload.bin": "ota_payload",
        }
        if base in partition_names:
            partitions.add(partition_names[base])
        for suffix in (".new.dat", ".new.dat.br", ".transfer.list"):
            if base.endswith(suffix):
                candidate = base.removesuffix(suffix)
                if _partition_signal(candidate):
                    partitions.add(candidate)
        for value in _METADATA_SIGNALS:
            if normalized.endswith(value):
                metadata.add(value)

    @staticmethod
    def _unsafe_finding(name: str) -> InspectionFinding:
        return InspectionFinding(
            "archive.unsafe_path",
            FindingSeverity.CRITICAL,
            "Unsafe archive path",
            f"{name} is absolute or traverses outside an extraction root. Extraction remains locked.",
        )

    @staticmethod
    def _link_finding(name: str) -> InspectionFinding:
        return InspectionFinding(
            "archive.link",
            FindingSeverity.WARNING,
            "Archive contains a link",
            f"{name} is a symbolic or hard link and requires containment policy before extraction.",
        )

    @staticmethod
    def _special_finding(name: str) -> InspectionFinding:
        return InspectionFinding(
            "archive.special_entry",
            FindingSeverity.CRITICAL,
            "Unsupported special archive entry",
            f"{name} is not a regular file or directory. Extraction remains locked.",
        )

    def _entry_limit(self, count: int) -> InspectionFinding:
        return InspectionFinding(
            "archive.entry_limit",
            FindingSeverity.CRITICAL,
            "Archive entry limit reached",
            f"Archive reports at least {count} entries; inspection stopped at {self.MAX_ARCHIVE_ENTRIES}.",
        )

    def _record_finding(
        self,
        findings: list[InspectionFinding],
        finding: InspectionFinding,
    ) -> None:
        finding = replace(
            finding,
            title=_bounded_text(finding.title, 160),
            detail=_bounded_text(finding.detail, 1024),
        )
        if len(findings) < self.MAX_FINDINGS:
            findings.append(finding)
        elif len(findings) == self.MAX_FINDINGS:
            findings.append(
                InspectionFinding(
                    "inspection.finding_limit",
                    FindingSeverity.CRITICAL,
                    "Finding limit reached",
                    f"Inspection retained the first {self.MAX_FINDINGS} findings and stopped adding details.",
                )
            )


class RomInspectionService:
    REPORT_NAME = "inspection.romverse"
    TREE_INDEX_NAME = "working-tree-index.romverse"
    MAX_REPORT_BYTES = 1024 * 1024
    MAX_TREE_INDEX_BYTES = 128 * 1024
    MAX_TREE_FILES = 200_000
    MAX_EXPANDED_BYTES = 256 * 1024 * 1024 * 1024
    MAX_EXPANSION_RATIO = 100
    MIN_FREE_RESERVE = 4 * 1024 * 1024 * 1024

    def __init__(self, store: RomProjectStore, inspector: RomInspector | None = None) -> None:
        self.store = store
        self.inspector = inspector or RomInspector()

    def inspect_project(
        self,
        project_id: str,
        progress: ProgressCallback | None = None,
    ) -> RomInspectionReport:
        project = self.store.get(project_id)
        if project.original is None:
            raise ProjectError("Import and verify an original before inspection")
        path = self.store.original_path(project_id)
        before = _file_identity(path)

        def publish_hash(done: int, total: int) -> None:
            if progress is not None and total > 0 and done < total:
                progress(done, total)

        verification = self.store.verify_original(
            project_id,
            publish_hash,
        )
        if not verification.valid:
            raise ProjectError(f"Original integrity check failed: {verification.status}")
        report = self._inspect_verified_source(project_id, path)
        if before != _file_identity(path):
            raise ProjectError("Protected original changed during structure inspection")
        report = self._seal_report(report)
        self._save(project_id, report)
        if progress is not None:
            terminal = path.stat().st_size or 1
            progress(terminal, terminal)
        return report

    def _inspect_verified_source(self, project_id: str, path: Path) -> RomInspectionReport:
        project = self.store.get(project_id)
        if project.original is None:
            raise ProjectError("Import and verify an original before inspection")
        return self.inspector.inspect(
            path,
            project.original.sha256,
            project.original.original_name,
        )

    def extract_project_tree(
        self,
        project_id: str,
        progress: ProgressCallback | None = None,
    ) -> Path:
        """Materialize a verified archive or recognized single image in a contained tree."""
        project = self.store.get(project_id)
        if project.original is None:
            raise ProjectError("Import and verify an original before extraction")
        source = self.store.original_path(project_id)
        source_identity = _file_identity(source)
        verification = self.store.verify_original(project_id)
        if not verification.valid:
            raise ProjectError(f"Original integrity check failed: {verification.status}")
        if source_identity != _file_identity(source):
            raise ProjectError("Protected original changed during extraction verification")
        report = self.load_report(project_id)
        if report is None or report.schema_version < 2:
            report = self._seal_report(self._inspect_verified_source(project_id, source))
            if source_identity != _file_identity(source):
                raise ProjectError("Protected original changed during structure inspection")
            self._save(project_id, report)
        if any(f.severity is FindingSeverity.CRITICAL for f in report.findings):
            raise ProjectError("Extraction blocked by critical structure findings")
        single_name = (
            ""
            if report.container in (ContainerKind.ZIP, ContainerKind.TAR)
            else _single_input_name(report)
        )
        budget = self.extraction_budget(project_id, report)
        if not budget.safe:
            raise ProjectError(budget.reason)
        root = self.store.working_root / project_id / "tree"
        self.store.get(project_id)
        parent = root.parent
        ensure_private_directory(parent, boundary=self.store.workspace)
        if os.path.lexists(root):
            raise ProjectError("An extracted working tree already exists or is unsafe")
        staging = root.with_name(f".tree-{uuid4().hex}")
        ensure_private_directory(staging, boundary=self.store.workspace)

        def publish_extracted_bytes(done: int, total: int) -> None:
            if progress is not None and total > 0 and done < total:
                progress(done, total)

        try:
            if report.container is ContainerKind.ZIP:
                self._extract_zip(
                    source,
                    staging,
                    budget.expected_bytes,
                    publish_extracted_bytes,
                )
            elif report.container is ContainerKind.TAR:
                self._extract_tar(
                    source,
                    staging,
                    budget.expected_bytes,
                    publish_extracted_bytes,
                )
            else:
                self._stage_single_input(
                    source,
                    _contained_target(staging, single_name),
                    project.original.sha256,
                    publish_extracted_bytes,
                )
            if source_identity != _file_identity(source):
                raise ProjectError("Protected original changed while the working tree was prepared")
            if os.path.lexists(root):
                raise ProjectError("An extracted working tree already exists or is unsafe")
            os.replace(staging, root)
            # Index the completed tree on this background worker. Normal page refreshes
            # can render its extraction summary without recursively walking a
            # multi-gigabyte filesystem on Qt's UI thread. Build planning deliberately
            # refreshes this index before deriving authoritative inputs or hashes.
            self.refresh_working_tree_summary(project_id)
            if progress is not None:
                terminal = budget.expected_bytes or 1
                progress(terminal, terminal)
            return root
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise

    def extraction_budget(
        self,
        project_id: str,
        report: RomInspectionReport | None = None,
    ) -> ExtractionBudget:
        project = self.store.get(project_id)
        report = report or self.load_report(project_id)
        if report is None:
            raise ProjectError("Inspect the archive before calculating extraction space")
        if (
            project.original is None
            or report.source_sha256 != project.original.sha256
            or report.source_name != project.original.original_name
            or not self._valid_report(report)
        ):
            raise ProjectError("Inspection evidence is unavailable or unsafe")
        source = self.store.original_path(project_id)
        free = shutil.disk_usage(self.store.workspace).free
        expected_bytes = (
            report.uncompressed_bytes
            if report.container in (ContainerKind.ZIP, ContainerKind.TAR)
            else source.stat().st_size
        )
        return self.calculate_extraction_budget(
            expected_bytes,
            source.stat().st_size,
            free,
        )

    @classmethod
    def calculate_extraction_budget(
        cls,
        expected_bytes: int,
        source_bytes: int,
        free_bytes: int,
    ) -> ExtractionBudget:
        expected = max(0, expected_bytes)
        source = max(1, source_bytes)
        free = max(0, free_bytes)
        reserve = max(cls.MIN_FREE_RESERVE, expected // 10)
        ratio = expected / source
        if expected > cls.MAX_EXPANDED_BYTES:
            reason = (
                f"Archive declares {_byte_label(expected)} expanded, above the "
                f"{_byte_label(cls.MAX_EXPANDED_BYTES)} Guardian hard limit"
            )
            safe = False
        elif expected > 4 * 1024 * 1024 * 1024 and ratio > cls.MAX_EXPANSION_RATIO:
            reason = (
                f"Archive expansion ratio {ratio:.0f}:1 exceeds the Guardian anti-zip-bomb limit"
            )
            safe = False
        elif free < expected + reserve:
            reason = (
                f"Extraction requires {_byte_label(expected + reserve)} free including "
                f"safety reserve; {_byte_label(free)} is available"
            )
            safe = False
        else:
            reason = (
                f"Extraction budget verified: {_byte_label(expected)} expanded, "
                f"{_byte_label(free)} free, {_byte_label(reserve)} retained as reserve"
            )
            safe = True
        return ExtractionBudget(
            expected,
            source,
            free,
            reserve,
            cls.MAX_EXPANDED_BYTES,
            safe,
            reason,
        )

    def working_tree_exists(self, project_id: str) -> bool:
        """Check tree containment in constant time without enumerating its contents."""

        self.store.get(project_id)
        root = self.store.working_root / project_id / "tree"
        try:
            if root.is_symlink() or not root.is_dir() or root.resolve(strict=True) != root:
                return False
        except OSError:
            return False
        return True

    def cached_working_tree_summary(self, project_id: str) -> WorkingTreeSummary | None:
        """Load the sealed display index without walking the extracted tree."""

        if not self.working_tree_exists(project_id):
            return None
        index = self._load_working_tree_index(project_id)
        if index is None:
            return None
        return WorkingTreeSummary(index.file_count, index.total_bytes, index.notable_files)

    def summarize_working_tree(self, project_id: str) -> WorkingTreeSummary | None:
        """Return an index, migrating a legacy tree with one full caller-owned scan."""

        summary = self.cached_working_tree_summary(project_id)
        if summary is not None:
            return summary
        if not self.working_tree_exists(project_id):
            return None
        return self.refresh_working_tree_summary(project_id)

    def refresh_working_tree_summary(self, project_id: str) -> WorkingTreeSummary | None:
        """Re-enumerate and seal the tree; call only from a background operation."""

        if not self.working_tree_exists(project_id):
            return None
        root = self.store.working_root / project_id / "tree"
        count = 0
        total = 0
        notable: list[str] = []
        try:
            for path in root.rglob("*"):
                if path.is_symlink() or not path.is_file():
                    continue
                count += 1
                if count > self.MAX_TREE_FILES:
                    return None
                total += path.stat().st_size
                if path.name.lower() in {
                    "boot.img",
                    "init_boot.img",
                    "vendor_boot.img",
                    "super.img",
                    "system.img",
                    "system_ext.img",
                    "product.img",
                    "vendor.img",
                    "odm.img",
                    "payload.bin",
                    "vbmeta.img",
                }:
                    notable.append(path.relative_to(root).as_posix())
        except OSError:
            return None
        summary = WorkingTreeSummary(count, total, tuple(sorted(notable)))
        # The index is a responsiveness/display cache, never execution evidence.
        # A hostile or read-only cache path must not turn a completely extracted tree
        # into a false failed operation after the atomic tree commit already happened.
        with suppress(ProjectError):
            self._save_working_tree_index(project_id, summary)
        return summary

    def _save_working_tree_index(
        self,
        project_id: str,
        summary: WorkingTreeSummary,
    ) -> None:
        project = self.store.get(project_id)
        if project.original is None:
            raise ProjectError("A protected original is required for the working-tree index")
        tree = self.store.working_root / project_id / "tree"
        payload: dict[str, object] = {
            "format": "romverse.working-tree-index",
            "schema_version": 1,
            "project_id": project_id,
            "source_sha256": project.original.sha256,
            "generated_at": datetime.now(UTC).isoformat(),
            "tree_relative_path": tree.relative_to(self.store.workspace).as_posix(),
            "file_count": summary.file_count,
            "total_bytes": summary.total_bytes,
            "notable_files": summary.notable_files,
        }
        payload["record_digest"] = _digest(payload)
        try:
            atomic_write_json(
                self.store.projects_root / project_id / self.TREE_INDEX_NAME,
                payload,
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_TREE_INDEX_BYTES,
            )
        except LocalStoreError as exc:
            raise ProjectError("Working-tree display index could not be preserved safely") from exc

    def _load_working_tree_index(self, project_id: str) -> WorkingTreeIndex | None:
        project = self.store.get(project_id)
        if project.original is None:
            return None
        path = self.store.projects_root / project_id / self.TREE_INDEX_NAME
        try:
            data = read_json_object(
                path,
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_TREE_INDEX_BYTES,
            )
        except (LocalStoreError, OSError):
            return None
        expected = {
            "format",
            "schema_version",
            "project_id",
            "source_sha256",
            "generated_at",
            "tree_relative_path",
            "file_count",
            "total_bytes",
            "notable_files",
            "record_digest",
        }
        if set(data) != expected or data.get("format") != "romverse.working-tree-index":
            return None
        unsigned = dict(data)
        digest = unsigned.pop("record_digest", None)
        if not _sha256_value(digest) or digest != _digest(unsigned):
            return None
        notable = data.get("notable_files")
        root = self.store.working_root / project_id / "tree"
        expected_tree = root.relative_to(self.store.workspace).as_posix()
        if not (
            data.get("schema_version") == 1
            and data.get("project_id") == project_id
            and data.get("source_sha256") == project.original.sha256
            and _aware_timestamp(data.get("generated_at"))
            and data.get("tree_relative_path") == expected_tree
            and type(data.get("file_count")) is int
            and 0 <= data["file_count"] <= self.MAX_TREE_FILES
            and type(data.get("total_bytes")) is int
            and 0 <= data["total_bytes"] <= self.MAX_EXPANDED_BYTES
            and isinstance(notable, list)
            and len(notable) <= 64
            and all(_safe_notable_path(value) for value in notable)
            and notable == sorted(set(notable))
        ):
            return None
        return WorkingTreeIndex(
            schema_version=1,
            project_id=project_id,
            source_sha256=project.original.sha256,
            generated_at=str(data["generated_at"]),
            tree_relative_path=expected_tree,
            file_count=int(data["file_count"]),
            total_bytes=int(data["total_bytes"]),
            notable_files=tuple(notable),
            record_digest=str(digest),
        )

    @staticmethod
    def _extract_zip(
        source: Path,
        root: Path,
        expected_bytes: int,
        progress: ProgressCallback | None = None,
    ) -> None:
        extracted = 0
        total = 0
        with zipfile.ZipFile(source) as archive:
            infos = archive.infolist()
            if len(infos) > RomInspector.MAX_ARCHIVE_ENTRIES:
                raise ProjectError("Archive exceeds the safe entry limit")
            for info in infos:
                mode = info.external_attr >> 16
                if (
                    _unsafe_path(info.filename)
                    or stat.S_ISLNK(mode)
                    or info.flag_bits & 0x1
                    or _unsupported_zip_type(info, mode)
                ):
                    raise ProjectError(f"Extraction blocked for unsafe entry: {info.filename}")
                total += max(0, info.file_size)
                if total > expected_bytes:
                    raise ProjectError(
                        "Archive expanded size changed after inspection; extraction stopped"
                    )
                target = _contained_target(root, info.filename)
                if info.is_dir():
                    _ensure_tree_directory(root, target)
                    continue
                _ensure_tree_directory(root, target.parent)
                with archive.open(info) as input_stream, target.open("xb") as output_stream:
                    while chunk := input_stream.read(4 * 1024 * 1024):
                        output_stream.write(chunk)
                        extracted += len(chunk)
                        if extracted > expected_bytes:
                            raise ProjectError(
                                "Archive produced more data than its inspected size; extraction stopped"
                            )
                        if progress is not None:
                            progress(min(extracted, expected_bytes), expected_bytes)
                ensure_private_file(target)

    @staticmethod
    def _extract_tar(
        source: Path,
        root: Path,
        expected_bytes: int,
        progress: ProgressCallback | None = None,
    ) -> None:
        extracted = 0
        total = 0
        with tarfile.open(source, mode="r:*") as archive:
            for count, member in enumerate(archive, start=1):
                if count > RomInspector.MAX_ARCHIVE_ENTRIES:
                    raise ProjectError("Archive exceeds the safe entry limit")
                if (
                    _unsafe_path(member.name)
                    or member.issym()
                    or member.islnk()
                    or not (member.isdir() or member.isfile())
                ):
                    raise ProjectError(f"Extraction blocked for unsafe entry: {member.name}")
                total += max(0, member.size)
                if total > expected_bytes:
                    raise ProjectError(
                        "Archive expanded size changed after inspection; extraction stopped"
                    )
                target = _contained_target(root, member.name)
                if member.isdir():
                    _ensure_tree_directory(root, target)
                elif member.isfile():
                    _ensure_tree_directory(root, target.parent)
                    stream = archive.extractfile(member)
                    if stream is None:
                        raise ProjectError(f"Unable to read archive entry: {member.name}")
                    with stream, target.open("xb") as output_stream:
                        while chunk := stream.read(4 * 1024 * 1024):
                            output_stream.write(chunk)
                            extracted += len(chunk)
                            if extracted > expected_bytes:
                                raise ProjectError(
                                    "Archive produced more data than its inspected size; extraction stopped"
                                )
                            if progress is not None:
                                progress(min(extracted, expected_bytes), expected_bytes)
                    ensure_private_file(target)

    @staticmethod
    def _stage_single_input(
        source: Path,
        target: Path,
        expected_sha256: str,
        progress: ProgressCallback | None = None,
    ) -> None:
        total = source.stat().st_size
        copied = 0
        digest = hashlib.sha256()
        with source.open("rb") as input_stream, target.open("xb") as output_stream:
            while chunk := input_stream.read(4 * 1024 * 1024):
                output_stream.write(chunk)
                digest.update(chunk)
                copied += len(chunk)
                if progress is not None:
                    progress(copied, total)
            output_stream.flush()
            os.fsync(output_stream.fileno())
        ensure_private_file(target)
        if digest.hexdigest() != expected_sha256:
            raise ProjectError("Staged firmware image failed source SHA-256 verification")

    def load_report(self, project_id: str) -> RomInspectionReport | None:
        project = self.store.get(project_id)
        path = self.store.projects_root / project.project_id / self.REPORT_NAME
        if not path.is_file():
            return None
        try:
            data = read_json_object(
                path,
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_REPORT_BYTES,
            )
            report_fields = {field.name for field in fields(RomInspectionReport)}
            schema_version = data.get("schema_version")
            expected_fields = (
                {"format", *report_fields}
                if schema_version == 2
                else {"format", *(report_fields - {"record_digest"})}
                if schema_version == 1
                else set()
            )
            if set(data) != expected_fields or data.pop("format") != "romverse.inspection":
                return None
            if not self._valid_raw_report(data):
                return None
            findings = tuple(
                InspectionFinding(
                    finding_id=item["finding_id"],
                    severity=FindingSeverity(item["severity"]),
                    title=item["title"],
                    detail=item["detail"],
                )
                for item in data["findings"]
            )
            report = RomInspectionReport(
                schema_version=schema_version,
                generated_at=data["generated_at"],
                source_sha256=data["source_sha256"],
                source_name=data["source_name"],
                container=ContainerKind(data["container"]),
                entry_count=data["entry_count"],
                uncompressed_bytes=data["uncompressed_bytes"],
                partition_signals=tuple(data["partition_signals"]),
                metadata_signals=tuple(data["metadata_signals"]),
                findings=findings,
                complete=data["complete"],
                record_digest=data.get("record_digest", ""),
            )
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            return None
        if (
            project.original is None
            or report.source_sha256 != project.original.sha256
            or report.source_name != project.original.original_name
            or not self._valid_report(report)
        ):
            return None
        return report

    def _save(self, project_id: str, report: RomInspectionReport) -> None:
        if report.schema_version != 2 or not self._valid_report(report):
            raise ProjectError("Inspection report metadata is invalid")
        directory = self.store.projects_root / project_id
        path = directory / self.REPORT_NAME
        payload = {"format": "romverse.inspection", **asdict(report)}
        atomic_write_json(
            path,
            payload,
            boundary=self.store.workspace,
            maximum_bytes=self.MAX_REPORT_BYTES,
        )

    @staticmethod
    def _seal_report(report: RomInspectionReport) -> RomInspectionReport:
        unsigned = replace(report, schema_version=2, record_digest="")
        payload = asdict(unsigned)
        payload.pop("record_digest")
        return replace(unsigned, record_digest=_digest(payload))

    @staticmethod
    def _valid_raw_report(data: dict[str, object]) -> bool:
        findings = data.get("findings")
        return bool(
            type(data.get("schema_version")) is int
            and isinstance(data.get("generated_at"), str)
            and isinstance(data.get("source_sha256"), str)
            and isinstance(data.get("source_name"), str)
            and isinstance(data.get("container"), str)
            and type(data.get("entry_count")) is int
            and type(data.get("uncompressed_bytes")) is int
            and isinstance(data.get("partition_signals"), list)
            and isinstance(data.get("metadata_signals"), list)
            and isinstance(findings, list)
            and all(
                isinstance(item, dict)
                and set(item) == {"finding_id", "severity", "title", "detail"}
                and all(isinstance(item[key], str) for key in item)
                for item in findings
            )
            and type(data.get("complete")) is bool
            and (data.get("schema_version") == 1 or isinstance(data.get("record_digest"), str))
        )

    @staticmethod
    def _valid_report(report: RomInspectionReport) -> bool:
        unsigned = asdict(report)
        digest = unsigned.pop("record_digest")
        partition_signals = tuple(report.partition_signals)
        metadata_signals = tuple(report.metadata_signals)
        return bool(
            type(report.schema_version) is int
            and report.schema_version in {1, 2}
            and _aware_timestamp(report.generated_at)
            and _sha256_value(report.source_sha256)
            and isinstance(report.source_name, str)
            and 1 <= len(report.source_name) <= 255
            and "\x00" not in report.source_name
            and isinstance(report.container, ContainerKind)
            and type(report.entry_count) is int
            and 0 <= report.entry_count < 2**63
            and type(report.uncompressed_bytes) is int
            and 0 <= report.uncompressed_bytes < 2**63
            and len(partition_signals) <= 32
            and partition_signals == tuple(sorted(set(partition_signals)))
            and all(_partition_signal(value) for value in partition_signals)
            and len(metadata_signals) <= 16
            and metadata_signals == tuple(sorted(set(metadata_signals)))
            and set(metadata_signals) <= _METADATA_SIGNALS
            and len(report.findings) <= RomInspector.MAX_FINDINGS + 1
            and all(_valid_finding(item) for item in report.findings)
            and type(report.complete) is bool
            and (not report.complete or report.entry_count <= RomInspector.MAX_ARCHIVE_ENTRIES)
            and (
                (report.schema_version == 1 and not digest)
                or (
                    report.schema_version == 2
                    and _sha256_value(digest)
                    and digest == _digest(unsigned)
                )
            )
        )


def _digest(payload: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


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


def _valid_finding(finding: InspectionFinding) -> bool:
    return bool(
        isinstance(finding, InspectionFinding)
        and re.fullmatch(r"[a-z0-9._-]{1,80}", finding.finding_id)
        and isinstance(finding.severity, FindingSeverity)
        and _valid_text(finding.title, 160)
        and _valid_text(finding.detail, 1024)
    )


def _valid_text(value: object, maximum: int) -> bool:
    return bool(
        isinstance(value, str)
        and 1 <= len(value) <= maximum
        and all(character.isprintable() or character == "\t" for character in value)
    )


def _bounded_text(value: str, maximum: int) -> str:
    cleaned = "".join(
        character if character.isprintable() or character == "\t" else "�"
        for character in str(value)
    )
    return (cleaned or "Unavailable")[:maximum]


def _partition_signal(value: object) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", value))


def _safe_notable_path(value: object) -> bool:
    if not isinstance(value, str) or not 1 <= len(value) <= 1024 or "\x00" in value:
        return False
    path = PurePosixPath(value)
    return bool(not path.is_absolute() and ".." not in path.parts and value == path.as_posix())


def _file_identity(path: Path) -> tuple[int, int, int, int]:
    details = path.lstat()
    if not stat.S_ISREG(details.st_mode):
        raise ProjectError("Protected original is not a regular file")
    return details.st_dev, details.st_ino, details.st_size, details.st_mtime_ns


def _unsupported_zip_type(info: zipfile.ZipInfo, mode: int) -> bool:
    file_type = stat.S_IFMT(mode)
    return bool(file_type and file_type not in {stat.S_IFREG, stat.S_IFDIR} and not info.is_dir())


def _unsafe_path(name: str) -> bool:
    path = PurePosixPath(name.replace("\\", "/"))
    return path.is_absolute() or ".." in path.parts


def _single_input_name(report: RomInspectionReport) -> str:
    if report.container is ContainerKind.ANDROID_PAYLOAD:
        return "payload.bin"
    supported = {
        "boot",
        "init_boot",
        "vendor_boot",
        "recovery",
        "super",
        "system",
        "system_ext",
        "product",
        "vendor",
        "odm",
        "vbmeta",
        "dtbo",
    }
    candidates = tuple(value for value in report.partition_signals if value in supported)
    if len(candidates) == 1:
        return f"{candidates[0]}.img"
    if not candidates:
        raise ProjectError(
            "This single-file input has no confirmed Android partition role; "
            "use a recognized payload.bin or named partition image"
        )
    raise ProjectError(
        "This single-file input reports multiple partition roles and cannot be staged safely"
    )


def _contained_target(root: Path, name: str) -> Path:
    target = (root / PurePosixPath(name)).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ProjectError(f"Archive entry escapes extraction root: {name}")
    return target


def _ensure_tree_directory(root: Path, target: Path) -> None:
    safe_root = root.resolve(strict=True)
    if not target.is_relative_to(safe_root):
        raise ProjectError("Archive directory escapes the extraction root")
    current = safe_root
    for part in target.relative_to(safe_root).parts:
        current /= part
        if os.path.lexists(current):
            details = current.lstat()
            if not stat.S_ISDIR(details.st_mode):
                raise ProjectError("Archive directory conflicts with an existing entry")
        else:
            ensure_private_directory(current, boundary=safe_root)


def _byte_label(value: int) -> str:
    size = float(max(0, value))
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TiB"
