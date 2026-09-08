from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import zipfile
from collections.abc import Callable
from dataclasses import asdict, dataclass, fields, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import BinaryIO

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


@dataclass(frozen=True, slots=True)
class ExternalPackageMemberEvidence:
    path: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class ExternalPackageIdentityFact:
    field: str
    value: str
    member_path: str


@dataclass(frozen=True, slots=True)
class ExternalPackageMetadataInventory:
    """Bounded package-declared evidence that can never become a procedure."""

    schema_version: int
    project_id: str
    created_at: str
    source_sha256: str
    metadata_members: tuple[ExternalPackageMemberEvidence, ...]
    identity_facts: tuple[ExternalPackageIdentityFact, ...]
    procedure_members: tuple[ExternalPackageMemberEvidence, ...]
    manifest_verified_paths: tuple[str, ...]
    identity_authority: str
    procedure_authority: str
    build_authority: str
    device_authority: str
    execution_authority: str
    bootloader_relock: str
    record_digest: str


class ExternalFirmwareIntakeService:
    """Hash and inspect one external package without importing or extracting it."""

    RECEIPT_NAME = "external-firmware-intake.romverse"
    FORMAT = "romverse.external-firmware-intake"
    INVENTORY_NAME = "external-package-metadata.romverse"
    INVENTORY_FORMAT = "romverse.external-package-metadata"
    AUTHORITY = "evidence-only-no-build-device-or-execution-authority"
    IDENTITY_AUTHORITY = "package-declared-unverified"
    PROCEDURE_AUTHORITY = "untrusted-presence-only-never-executable"
    MAX_RECEIPT_BYTES = 256 * 1024
    MAX_INVENTORY_BYTES = 512 * 1024
    MAX_SOURCE_BYTES = 2 * 1024 * 1024 * 1024 * 1024
    CHUNK_SIZE = 4 * 1024 * 1024
    MAX_METADATA_MEMBER_BYTES = 256 * 1024
    MAX_METADATA_TOTAL_BYTES = 1024 * 1024
    MAX_PROCEDURE_MEMBER_BYTES = 8 * 1024 * 1024
    MAX_PROCEDURE_TOTAL_BYTES = 64 * 1024 * 1024
    MAX_PROCEDURE_MEMBERS = 256
    METADATA_PATHS = frozenset(
        {"build-info.txt", "customization-manifest.tsv", "sha256sums", "android-info.txt"}
    )
    IDENTITY_KEYS = {
        "manufacturer": "manufacturer",
        "oem": "manufacturer",
        "brand": "manufacturer",
        "codename": "codename",
        "device": "codename",
        "product": "codename",
        "require product": "codename",
        "build": "build_id",
        "build_id": "build_id",
        "firmware": "build_id",
        "firmware_version": "build_id",
        "version": "build_id",
        "android": "android_version",
        "android_version": "android_version",
        "region": "region",
        "channel": "channel",
        "base": "base_provenance",
        "base_build": "base_provenance",
        "base_provenance": "base_provenance",
    }

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
                inventory = self._inventory(
                    stream,
                    project_id=project_id,
                    source_sha256=digest.hexdigest(),
                    container=report.container,
                    inspection_complete=report.complete,
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
        self._save_inventory(inventory)
        atomic_write_json(
            self.store.projects_root / project_id / self.RECEIPT_NAME,
            {"format": self.FORMAT, **asdict(receipt)},
            boundary=self.store.workspace,
            maximum_bytes=self.MAX_RECEIPT_BYTES,
        )
        loaded = self.load(project_id)
        if loaded != receipt:
            raise ProjectError("External firmware intake evidence failed durable verification")
        if self.load_inventory(project_id) != inventory:
            raise ProjectError("External package metadata evidence failed durable verification")
        if progress is not None:
            progress(path_after.st_size, path_after.st_size)
        return receipt

    def load_inventory(self, project_id: str) -> ExternalPackageMetadataInventory | None:
        path = self.store.projects_root / project_id / self.INVENTORY_NAME
        try:
            payload = read_json_object(
                path,
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_INVENTORY_BYTES,
            )
            expected = {
                "format",
                *(field.name for field in fields(ExternalPackageMetadataInventory)),
            }
            if set(payload) != expected or payload.pop("format") != self.INVENTORY_FORMAT:
                return None
            for name, record_type in (
                ("metadata_members", ExternalPackageMemberEvidence),
                ("identity_facts", ExternalPackageIdentityFact),
                ("procedure_members", ExternalPackageMemberEvidence),
            ):
                values = payload.get(name)
                if not isinstance(values, list):
                    return None
                expected_fields = {field.name for field in fields(record_type)}
                if any(
                    not isinstance(value, dict) or set(value) != expected_fields for value in values
                ):
                    return None
                payload[name] = tuple(record_type(**value) for value in values)
            verified = payload.get("manifest_verified_paths")
            if not isinstance(verified, list) or not all(
                isinstance(item, str) for item in verified
            ):
                return None
            payload["manifest_verified_paths"] = tuple(verified)
            inventory = ExternalPackageMetadataInventory(**payload)
            receipt = self.load(project_id)
        except (OSError, TypeError, ValueError, KeyError, ProjectError):
            return None
        unsigned = asdict(inventory)
        digest = unsigned.pop("record_digest")
        members = (*inventory.metadata_members, *inventory.procedure_members)
        if (
            receipt is None
            or type(inventory.schema_version) is not int
            or inventory.schema_version != 1
            or inventory.project_id != project_id
            or inventory.source_sha256 != receipt.source_sha256
            or not _aware_timestamp(inventory.created_at)
            or len(inventory.metadata_members) > len(self.METADATA_PATHS)
            or len(inventory.identity_facts) > len(set(self.IDENTITY_KEYS.values()))
            or len(inventory.procedure_members) > self.MAX_PROCEDURE_MEMBERS
            or any(not self._valid_member(item) for item in members)
            or any(
                item.path.casefold() not in self.METADATA_PATHS
                or item.size_bytes > self.MAX_METADATA_MEMBER_BYTES
                for item in inventory.metadata_members
            )
            or sum(item.size_bytes for item in inventory.metadata_members)
            > self.MAX_METADATA_TOTAL_BYTES
            or any(
                not _procedure_path(item.path.casefold())
                or item.size_bytes > self.MAX_PROCEDURE_MEMBER_BYTES
                for item in inventory.procedure_members
            )
            or sum(item.size_bytes for item in inventory.procedure_members)
            > self.MAX_PROCEDURE_TOTAL_BYTES
            or tuple(sorted(item.path for item in inventory.metadata_members))
            != tuple(item.path for item in inventory.metadata_members)
            or len({item.path.casefold() for item in members}) != len(members)
            or tuple(sorted(item.path for item in inventory.procedure_members))
            != tuple(item.path for item in inventory.procedure_members)
            or any(not self._valid_fact(item) for item in inventory.identity_facts)
            or len({item.field for item in inventory.identity_facts})
            != len(inventory.identity_facts)
            or any(
                item.member_path not in {member.path for member in inventory.metadata_members}
                for item in inventory.identity_facts
            )
            or tuple(sorted((item.field, item.member_path) for item in inventory.identity_facts))
            != tuple((item.field, item.member_path) for item in inventory.identity_facts)
            or not _sorted_unique(inventory.manifest_verified_paths, 512, 4096)
            or any(
                path not in {member.path for member in members}
                for path in inventory.manifest_verified_paths
            )
            or inventory.identity_authority != self.IDENTITY_AUTHORITY
            or inventory.procedure_authority != self.PROCEDURE_AUTHORITY
            or inventory.build_authority != "none"
            or inventory.device_authority != "none"
            or inventory.execution_authority != "none"
            or inventory.bootloader_relock != "never"
            or not _sha256(digest)
            or digest != _digest(unsigned)
        ):
            return None
        return inventory

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

    def _inventory(
        self,
        stream: BinaryIO,
        *,
        project_id: str,
        source_sha256: str,
        container: ContainerKind,
        inspection_complete: bool,
    ) -> ExternalPackageMetadataInventory:
        metadata_members: list[ExternalPackageMemberEvidence] = []
        identity_facts: list[ExternalPackageIdentityFact] = []
        procedures: list[ExternalPackageMemberEvidence] = []
        verified_paths: set[str] = set()
        if container is ContainerKind.ZIP:
            if not inspection_complete:
                raise ProjectError(
                    "External ZIP metadata inventory requires complete structure evidence"
                )
            stream.seek(0)
            try:
                with zipfile.ZipFile(stream) as archive:
                    relevant: dict[str, zipfile.ZipInfo] = {}
                    procedure_count = 0
                    for info in archive.infolist():
                        if info.is_dir():
                            continue
                        raw_key = info.filename.casefold()
                        if raw_key not in self.METADATA_PATHS and not _procedure_path(raw_key):
                            continue
                        path = _safe_member_path(info.filename)
                        key = path.casefold()
                        is_procedure = _procedure_path(key)
                        mode = (info.external_attr >> 16) & 0xFFFF
                        if stat.S_IFMT(mode) not in {0, stat.S_IFREG}:
                            raise ProjectError(
                                "External package evidence member is not a regular file"
                            )
                        if key in relevant:
                            raise ProjectError(
                                "External package contains an ambiguous duplicate evidence path"
                            )
                        relevant[key] = info
                        if is_procedure:
                            procedure_count += 1
                            if procedure_count > self.MAX_PROCEDURE_MEMBERS:
                                raise ProjectError(
                                    "External package procedure inventory exceeds its bounded count"
                                )

                    metadata_payloads: dict[str, bytes] = {}
                    metadata_total = 0
                    procedure_total = 0
                    for key, info in sorted(relevant.items()):
                        if key in self.METADATA_PATHS:
                            metadata_total += info.file_size
                            if (
                                info.file_size > self.MAX_METADATA_MEMBER_BYTES
                                or metadata_total > self.MAX_METADATA_TOTAL_BYTES
                            ):
                                raise ProjectError(
                                    "External package metadata exceeds its bounded size"
                                )
                            evidence, payload = self._read_zip_member(
                                archive, info, self.MAX_METADATA_MEMBER_BYTES, retain=True
                            )
                            metadata_members.append(evidence)
                            metadata_payloads[key] = payload
                        else:
                            procedure_total += info.file_size
                            if (
                                info.file_size > self.MAX_PROCEDURE_MEMBER_BYTES
                                or procedure_total > self.MAX_PROCEDURE_TOTAL_BYTES
                            ):
                                raise ProjectError(
                                    "External package procedure evidence exceeds its bounded size"
                                )
                            evidence, _payload = self._read_zip_member(
                                archive, info, self.MAX_PROCEDURE_MEMBER_BYTES, retain=False
                            )
                            procedures.append(evidence)

                    seen_fields: set[str] = set()
                    for member in metadata_members:
                        key = member.path.casefold()
                        if key == "sha256sums":
                            continue
                        for fact in self._parse_identity(member.path, metadata_payloads[key]):
                            if fact.field in seen_fields:
                                raise ProjectError(
                                    "External package declares a duplicate identity field"
                                )
                            seen_fields.add(fact.field)
                            identity_facts.append(fact)
                    manifest = metadata_payloads.get("sha256sums")
                    if manifest is not None:
                        declared = self._parse_manifest(manifest)
                        for member in (*metadata_members, *procedures):
                            if member.path.casefold() == "sha256sums":
                                continue
                            expected = declared.get(member.path.casefold())
                            if expected is None:
                                continue
                            if expected != member.sha256:
                                raise ProjectError(
                                    "External package SHA256SUMS disagrees with inventoried content"
                                )
                            verified_paths.add(member.path)
            except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
                raise ProjectError(
                    "External package metadata could not be inspected safely"
                ) from exc

        payload: dict[str, object] = {
            "schema_version": 1,
            "project_id": project_id,
            "created_at": datetime.now(UTC).isoformat(),
            "source_sha256": source_sha256,
            "metadata_members": tuple(sorted(metadata_members, key=lambda item: item.path)),
            "identity_facts": tuple(
                sorted(identity_facts, key=lambda item: (item.field, item.member_path))
            ),
            "procedure_members": tuple(sorted(procedures, key=lambda item: item.path)),
            "manifest_verified_paths": tuple(sorted(verified_paths)),
            "identity_authority": self.IDENTITY_AUTHORITY,
            "procedure_authority": self.PROCEDURE_AUTHORITY,
            "build_authority": "none",
            "device_authority": "none",
            "execution_authority": "none",
            "bootloader_relock": "never",
        }
        digest_payload = dict(payload)
        for name in ("metadata_members", "identity_facts", "procedure_members"):
            digest_payload[name] = tuple(asdict(item) for item in payload[name])  # type: ignore[union-attr]
        return ExternalPackageMetadataInventory(  # type: ignore[arg-type]
            **payload,
            record_digest=_digest(digest_payload),
        )

    def _save_inventory(self, inventory: ExternalPackageMetadataInventory) -> None:
        atomic_write_json(
            self.store.projects_root / inventory.project_id / self.INVENTORY_NAME,
            {"format": self.INVENTORY_FORMAT, **asdict(inventory)},
            boundary=self.store.workspace,
            maximum_bytes=self.MAX_INVENTORY_BYTES,
        )

    @classmethod
    def _read_zip_member(
        cls,
        archive: zipfile.ZipFile,
        info: zipfile.ZipInfo,
        maximum: int,
        *,
        retain: bool,
    ) -> tuple[ExternalPackageMemberEvidence, bytes]:
        if info.flag_bits & 0x1 or info.file_size < 0 or info.file_size > maximum:
            raise ProjectError("External package evidence member is encrypted or oversized")
        digest = hashlib.sha256()
        captured = bytearray()
        total = 0
        with archive.open(info, "r") as member:
            while chunk := member.read(min(cls.CHUNK_SIZE, maximum + 1 - total)):
                total += len(chunk)
                if total > maximum:
                    raise ProjectError(
                        "External package evidence member exceeded its declared bound"
                    )
                digest.update(chunk)
                if retain:
                    captured.extend(chunk)
        if total != info.file_size:
            raise ProjectError("External package evidence member size changed during inspection")
        return (
            ExternalPackageMemberEvidence(info.filename, total, digest.hexdigest()),
            bytes(captured),
        )

    @classmethod
    def _parse_identity(
        cls, member_path: str, payload: bytes
    ) -> tuple[ExternalPackageIdentityFact, ...]:
        if b"\x00" in payload:
            raise ProjectError("External package metadata contains a NUL byte")
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ProjectError("External package metadata is not valid UTF-8") from exc
        facts: list[ExternalPackageIdentityFact] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            separator = (
                "\t" if member_path.casefold().endswith(".tsv") else "=" if "=" in line else ":"
            )
            if separator not in line:
                raise ProjectError("External package metadata contains a malformed line")
            raw_key, raw_value = (part.strip() for part in line.split(separator, 1))
            key = re.sub(r"[-.]+", "_", raw_key.casefold())
            field = cls.IDENTITY_KEYS.get(key)
            if field is None:
                continue
            if not _safe_identity_value(raw_value):
                raise ProjectError("External package identity contains unsafe command-like text")
            facts.append(ExternalPackageIdentityFact(field, raw_value, member_path))
        return tuple(facts)

    @staticmethod
    def _parse_manifest(payload: bytes) -> dict[str, str]:
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ProjectError("External package SHA256SUMS is not valid UTF-8") from exc
        declared: dict[str, str] = {}
        for line in text.splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            match = re.fullmatch(r"\s*([0-9a-fA-F]{64})\s+[ *](\S[^\r\n]*)\s*", line)
            if match is None:
                raise ProjectError("External package SHA256SUMS contains a malformed line")
            path = _safe_member_path(match.group(2)).casefold()
            if path in declared:
                raise ProjectError("External package SHA256SUMS contains a duplicate path")
            declared[path] = match.group(1).casefold()
        return declared

    @staticmethod
    def _valid_member(member: ExternalPackageMemberEvidence) -> bool:
        try:
            path = _safe_member_path(member.path)
        except ProjectError:
            return False
        return bool(
            path == member.path
            and type(member.size_bytes) is int
            and 0 <= member.size_bytes <= ExternalFirmwareIntakeService.MAX_PROCEDURE_MEMBER_BYTES
            and _sha256(member.sha256)
        )

    @classmethod
    def _valid_fact(cls, fact: ExternalPackageIdentityFact) -> bool:
        return bool(
            fact.field in set(cls.IDENTITY_KEYS.values())
            and _safe_identity_value(fact.value)
            and _valid_text(fact.member_path, 4096)
        )


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


def _safe_member_path(value: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 4096
        or "\\" in value
        or "\x00" in value
    ):
        raise ProjectError("External package evidence path is invalid")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ProjectError("External package evidence path is unsafe")
    return path.as_posix()


def _procedure_path(path: str) -> bool:
    return bool(
        path == "meta-inf/com/google/android/updater-script"
        or PurePosixPath(path).suffix in {".sh", ".bat", ".cmd", ".ps1"}
    )


def _safe_identity_value(value: object) -> bool:
    if not isinstance(value, str) or not 1 <= len(value) <= 256:
        return False
    if any(ord(character) < 32 for character in value):
        return False
    normalized = value.casefold()
    return not bool(
        re.search(r"\b(?:relock|flashing\s+lock|oem\s+lock)\b", normalized)
        or re.search(r"(?:&&|\|\||[;`$])", value)
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
