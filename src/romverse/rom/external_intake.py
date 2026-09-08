from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections.abc import Callable
from dataclasses import asdict, dataclass, fields, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from romverse.infrastructure.local_store import atomic_write_json, read_json_object
from romverse.rom.inspection import ContainerKind, FindingSeverity, RomInspector
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore
from romverse.rom.source_identity import identify_firmware_source

ProgressCallback = Callable[[int, int], None]


@dataclass(frozen=True, slots=True)
class ExternalFirmwareIntakeReceipt:
    """Authority-free evidence for a firmware file inspected at its existing path."""

    schema_version: int
    project_id: str
    created_at: str
    source_name: str
    source_path: str
    source_size_bytes: int
    source_modified_ns: int
    source_device: int
    source_inode: int
    source_mode: int
    source_sha256: str
    container: str
    entry_count: int
    uncompressed_bytes: int
    partition_signals: tuple[str, ...]
    metadata_signals: tuple[str, ...]
    finding_ids: tuple[str, ...]
    information_count: int
    warning_count: int
    critical_count: int
    inspection_complete: bool
    package_type: str
    identity_confidence: str
    manufacturer: str
    codename: str
    build_id: str
    android_version: str
    region: str
    identity_evidence: tuple[str, ...]
    authority: str
    source_copied: bool
    source_extracted: bool
    phone_changed: bool
    bootloader_relock: str
    record_digest: str


class ExternalFirmwareIntakeService:
    """Hash and inspect one external package without importing or extracting it."""

    RECEIPT_NAME = "external-firmware-intake.romverse"
    FORMAT = "romverse.external-firmware-intake"
    AUTHORITY = "evidence-only-no-build-device-or-execution-authority"
    MAX_RECEIPT_BYTES = 256 * 1024
    MAX_SOURCE_BYTES = 2 * 1024 * 1024 * 1024 * 1024
    CHUNK_SIZE = 4 * 1024 * 1024

    def __init__(self, store: RomProjectStore) -> None:
        self.store = store

    def inspect(
        self,
        project_id: str,
        selected: Path,
        progress: ProgressCallback | None = None,
    ) -> ExternalFirmwareIntakeReceipt:
        project = self.store.get(project_id)
        if project.original is not None:
            raise ProjectError(
                "External read-only intake is available only before a protected original is imported"
            )
        unresolved = selected.expanduser()
        if unresolved.is_symlink():
            raise ProjectError("External firmware cannot be a symbolic link")
        try:
            source = unresolved.resolve(strict=True)
            path_before = source.stat()
        except OSError as exc:
            raise ProjectError("External firmware is unavailable") from exc
        if source.is_relative_to(self.store.workspace):
            raise ProjectError("Choose firmware outside the current disposable workspace")
        if not source.is_file() or not stat.S_ISREG(path_before.st_mode):
            raise ProjectError("External firmware must be a regular file")
        if not 0 < path_before.st_size <= self.MAX_SOURCE_BYTES:
            raise ProjectError("External firmware size is outside the supported 2 TiB boundary")

        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(source, flags)
        except OSError as exc:
            raise ProjectError("External firmware could not be opened safely") from exc
        digest = hashlib.sha256()
        completed = 0
        try:
            with os.fdopen(descriptor, "rb", closefd=True) as stream:
                stream_before = os.fstat(stream.fileno())
                if not stat.S_ISREG(stream_before.st_mode) or not _same_file(
                    path_before, stream_before
                ):
                    raise ProjectError("External firmware changed before hashing began")
                while chunk := stream.read(self.CHUNK_SIZE):
                    digest.update(chunk)
                    completed += len(chunk)
                    if progress is not None and completed < path_before.st_size:
                        progress(completed, path_before.st_size)
                report = RomInspector().inspect_stream(
                    stream,
                    digest.hexdigest(),
                    source.name,
                )
                stream_after = os.fstat(stream.fileno())
                if completed != path_before.st_size or not _same_file(stream_before, stream_after):
                    raise ProjectError("External firmware changed while it was being inspected")
        except OSError as exc:
            raise ProjectError("External firmware could not be read safely") from exc

        try:
            path_after = source.stat()
        except OSError as exc:
            raise ProjectError("External firmware disappeared during inspection") from exc
        if not _same_file(path_before, path_after):
            raise ProjectError("External firmware changed during bounded inspection")

        identity = identify_firmware_source(source.name)
        severity_counts = {
            severity: sum(item.severity is severity for item in report.findings)
            for severity in FindingSeverity
        }
        now = datetime.now(UTC).isoformat()
        receipt = ExternalFirmwareIntakeReceipt(
            schema_version=1,
            project_id=project_id,
            created_at=now,
            source_name=source.name,
            source_path=str(source),
            source_size_bytes=path_after.st_size,
            source_modified_ns=path_after.st_mtime_ns,
            source_device=path_after.st_dev,
            source_inode=path_after.st_ino,
            source_mode=stat.S_IMODE(path_after.st_mode),
            source_sha256=digest.hexdigest(),
            container=report.container.value,
            entry_count=report.entry_count,
            uncompressed_bytes=report.uncompressed_bytes,
            partition_signals=tuple(report.partition_signals),
            metadata_signals=tuple(report.metadata_signals),
            finding_ids=tuple(sorted({item.finding_id for item in report.findings})),
            information_count=severity_counts[FindingSeverity.INFORMATION],
            warning_count=severity_counts[FindingSeverity.WARNING],
            critical_count=severity_counts[FindingSeverity.CRITICAL],
            inspection_complete=report.complete,
            package_type=identity.package_type,
            identity_confidence=identity.confidence,
            manufacturer=identity.manufacturer,
            codename=identity.codename,
            build_id=identity.build_id,
            android_version=identity.android_version,
            region=identity.region,
            identity_evidence=tuple(identity.evidence),
            authority=self.AUTHORITY,
            source_copied=False,
            source_extracted=False,
            phone_changed=False,
            bootloader_relock="never",
            record_digest="",
        )
        unsigned = asdict(receipt)
        unsigned.pop("record_digest")
        receipt = replace(receipt, record_digest=_digest(unsigned))
        atomic_write_json(
            self.store.projects_root / project_id / self.RECEIPT_NAME,
            {"format": self.FORMAT, **asdict(receipt)},
            boundary=self.store.workspace,
            maximum_bytes=self.MAX_RECEIPT_BYTES,
        )
        loaded = self.load(project_id)
        if loaded != receipt:
            raise ProjectError("External firmware intake evidence failed durable verification")
        if progress is not None:
            progress(path_after.st_size, path_after.st_size)
        return receipt

    def load(self, project_id: str) -> ExternalFirmwareIntakeReceipt | None:
        path = self.store.projects_root / project_id / self.RECEIPT_NAME
        try:
            payload = read_json_object(
                path,
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_RECEIPT_BYTES,
            )
            expected = {"format", *(field.name for field in fields(ExternalFirmwareIntakeReceipt))}
            if set(payload) != expected or payload.pop("format") != self.FORMAT:
                return None
            for key in (
                "partition_signals",
                "metadata_signals",
                "finding_ids",
                "identity_evidence",
            ):
                value = payload.get(key)
                if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                    return None
                payload[key] = tuple(value)
            receipt = ExternalFirmwareIntakeReceipt(**payload)
            project = self.store.get(project_id)
            source = Path(receipt.source_path)
            if source.is_symlink():
                return None
            resolved = source.resolve(strict=True)
            current = resolved.stat()
        except (OSError, TypeError, ValueError, KeyError, ProjectError):
            return None
        unsigned = asdict(receipt)
        digest = unsigned.pop("record_digest")
        if (
            project.original is not None
            or receipt.schema_version != 1
            or receipt.project_id != project_id
            or not _aware_timestamp(receipt.created_at)
            or not source.is_absolute()
            or resolved != source
            or resolved.is_relative_to(self.store.workspace)
            or not _valid_text(receipt.source_path, 4096)
            or receipt.source_name != resolved.name
            or not _valid_text(receipt.source_name, 255)
            or type(receipt.source_size_bytes) is not int
            or not 0 < receipt.source_size_bytes <= self.MAX_SOURCE_BYTES
            or type(receipt.source_modified_ns) is not int
            or receipt.source_modified_ns < 0
            or type(receipt.source_device) is not int
            or receipt.source_device < 0
            or type(receipt.source_inode) is not int
            or receipt.source_inode < 0
            or type(receipt.source_mode) is not int
            or not 0 <= receipt.source_mode <= 0o7777
            or not stat.S_ISREG(current.st_mode)
            or current.st_size != receipt.source_size_bytes
            or current.st_mtime_ns != receipt.source_modified_ns
            or current.st_dev != receipt.source_device
            or current.st_ino != receipt.source_inode
            or stat.S_IMODE(current.st_mode) != receipt.source_mode
            or not _sha256(receipt.source_sha256)
            or receipt.container not in {item.value for item in ContainerKind}
            or not 0 <= receipt.entry_count < 2**63
            or not 0 <= receipt.uncompressed_bytes < 2**63
            or not _sorted_unique(receipt.partition_signals, 32, 80)
            or not _sorted_unique(receipt.metadata_signals, 32, 160)
            or not _sorted_unique(receipt.finding_ids, RomInspector.MAX_FINDINGS + 1, 80)
            or any(
                type(value) is not int or not 0 <= value <= RomInspector.MAX_FINDINGS + 1
                for value in (
                    receipt.information_count,
                    receipt.warning_count,
                    receipt.critical_count,
                )
            )
            or type(receipt.inspection_complete) is not bool
            or not _valid_text(receipt.package_type, 200)
            or receipt.identity_confidence not in {"unknown", "high"}
            or any(
                not _optional_text(value, maximum)
                for value, maximum in (
                    (receipt.manufacturer, 100),
                    (receipt.codename, 100),
                    (receipt.build_id, 160),
                    (receipt.android_version, 80),
                    (receipt.region, 100),
                )
            )
            or len(receipt.identity_evidence) > 16
            or any(not _valid_text(value, 500) for value in receipt.identity_evidence)
            or receipt.authority != self.AUTHORITY
            or receipt.source_copied is not False
            or receipt.source_extracted is not False
            or receipt.phone_changed is not False
            or receipt.bootloader_relock != "never"
            or not _sha256(digest)
            or digest != _digest(unsigned)
        ):
            return None
        return receipt


def _same_file(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        left.st_dev,
        left.st_ino,
        left.st_size,
        left.st_mtime_ns,
        stat.S_IMODE(left.st_mode),
    ) == (
        right.st_dev,
        right.st_ino,
        right.st_size,
        right.st_mtime_ns,
        stat.S_IMODE(right.st_mode),
    )


def _digest(payload: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _sha256(value: object) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[0-9a-f]{64}", value))


def _aware_timestamp(value: object) -> bool:
    if not isinstance(value, str) or len(value) > 80:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed <= datetime.now(UTC) + timedelta(minutes=5)


def _valid_text(value: object, maximum: int) -> bool:
    return isinstance(value, str) and 1 <= len(value) <= maximum and "\x00" not in value


def _optional_text(value: object, maximum: int) -> bool:
    return isinstance(value, str) and len(value) <= maximum and "\x00" not in value


def _sorted_unique(values: tuple[str, ...], maximum_items: int, maximum_text: int) -> bool:
    return bool(
        isinstance(values, tuple)
        and len(values) <= maximum_items
        and values == tuple(sorted(set(values)))
        and all(_valid_text(value, maximum_text) for value in values)
    )
