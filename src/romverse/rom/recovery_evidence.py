from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, fields, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from romverse.core.privacy import WorkspacePrivacy
from romverse.device.models import AndroidDevice, DeviceState
from romverse.infrastructure.local_store import atomic_write_json, read_json_object
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore

ProgressCallback = Callable[[int, int], None]


@dataclass(frozen=True, slots=True)
class RecoveryArtifactEvidence:
    role: str
    display_name: str
    size_bytes: int
    modified_ns: int
    sha256: str
    verified_at: str
    provenance: str = "external-file"
    device_key: str = ""
    coverage: str = ""
    source_receipt_digest: str = ""


@dataclass(frozen=True, slots=True)
class RecoveryEvidenceRecord:
    schema_version: int
    project_id: str
    device_pack_id: str
    source_original_sha256: str
    created_at: str
    updated_at: str
    external_backup: RecoveryArtifactEvidence | None
    stock_recovery: RecoveryArtifactEvidence | None
    phone_changed: bool = False
    record_digest: str = ""


@dataclass(frozen=True, slots=True)
class RecoveryEvidenceAssessment:
    ready: bool
    external_backup_ready: bool
    stock_recovery_ready: bool
    evidence: tuple[str, ...]


class RecoveryEvidenceService:
    """Register and revalidate external recovery files without copying or using a phone."""

    RECEIPT_NAME = "recovery-evidence.romverse"
    LOCATOR_NAME = ".recovery-evidence-locators.json"
    ROLES = frozenset({"external_backup", "stock_recovery"})
    CHUNK_SIZE = 4 * 1024 * 1024
    MAX_ARTIFACT_BYTES = 2 * 1024 * 1024 * 1024 * 1024
    MAX_RECEIPT_BYTES = 256 * 1024
    MAX_LOCATOR_BYTES = 64 * 1024

    def __init__(self, store: RomProjectStore) -> None:
        self.store = store

    def register(
        self,
        project_id: str,
        role: str,
        source: Path,
        progress: ProgressCallback | None = None,
    ) -> RecoveryEvidenceRecord:
        project = self.store.get(project_id)
        if project.original is None:
            raise ProjectError("Import a protected firmware source before recovery evidence")
        if role not in self.ROLES:
            raise ProjectError("Unknown recovery-evidence role")
        path = source.expanduser()
        if path.is_symlink():
            raise ProjectError("Recovery evidence cannot be a symbolic link")
        try:
            path = path.resolve(strict=True)
            before = path.stat()
        except OSError as exc:
            raise ProjectError("Recovery evidence file is unavailable") from exc
        if path.is_relative_to(self.store.workspace):
            raise ProjectError("Recovery evidence must be stored outside the ROMVERSE workspace")
        if not path.is_file() or before.st_size <= 0:
            raise ProjectError("Recovery evidence must be a non-empty regular file")
        if before.st_size > self.MAX_ARTIFACT_BYTES:
            raise ProjectError("Recovery evidence exceeds the supported 2 TiB limit")

        def publish_hash(done: int, total: int) -> None:
            if progress is not None and total > 0 and done < total:
                progress(done, total)

        digest = _sha256(path, publish_hash)
        if role == "stock_recovery" and digest != project.original.sha256:
            raise ProjectError(
                "Stock recovery package does not match the protected firmware SHA-256"
            )
        after = path.stat()
        if (
            before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
            or before.st_ino != after.st_ino
        ):
            raise ProjectError("Recovery evidence changed while it was being verified")

        now = datetime.now(UTC).isoformat()
        current = self.load(project_id)
        if current is None:
            current = RecoveryEvidenceRecord(
                2,
                project_id,
                project.device_pack_id,
                project.original.sha256 if project.original else "",
                now,
                now,
                None,
                None,
                False,
                "",
            )
        elif current.schema_version == 1:
            raise ProjectError(
                "Verify the preserved legacy recovery evidence before registering another file"
            )
        artifact = RecoveryArtifactEvidence(
            role,
            path.name,
            after.st_size,
            after.st_mtime_ns,
            digest,
            now,
        )
        updated = replace(
            current,
            updated_at=now,
            external_backup=artifact if role == "external_backup" else current.external_backup,
            stock_recovery=artifact if role == "stock_recovery" else current.stock_recovery,
        )
        locators = self._load_locators(project_id)
        locators[role] = str(path)
        saved = self._save(project_id, updated, locators)
        if progress is not None:
            progress(after.st_size, after.st_size)
        return saved

    def register_phone_media_backup(
        self,
        project_id: str,
        source: Path,
        receipt,
        progress: ProgressCallback | None = None,
    ) -> RecoveryEvidenceRecord:
        """Register a ROMVERSE-created backup with its privacy-safe phone binding."""

        from romverse.backup.media import PhoneMediaBackupReceipt, PhoneMediaBackupService

        if not isinstance(receipt, PhoneMediaBackupReceipt):
            raise ProjectError("Local phone backup returned no verifiable ROMVERSE receipt")
        PhoneMediaBackupService.verify_receipt(source, receipt)
        if not re.fullmatch(r"[0-9a-f]{20}", receipt.device_key):
            raise ProjectError("Local phone backup receipt has no valid device binding")

        def publish_registration(done: int, total: int) -> None:
            if progress is not None and total > 0 and done < total:
                progress(done, total)

        record = self.register(
            project_id,
            "external_backup",
            source,
            publish_registration,
        )
        artifact = record.external_backup
        if artifact is None:
            raise ProjectError("Local phone backup evidence was not recorded")
        updated = replace(
            record,
            external_backup=replace(
                artifact,
                provenance="romverse-phone-media",
                device_key=receipt.device_key,
                coverage=receipt.coverage,
                source_receipt_digest=receipt.receipt_digest,
            ),
            updated_at=datetime.now(UTC).isoformat(),
        )
        saved = self._save(project_id, updated, self._load_locators(project_id))
        if progress is not None:
            terminal = artifact.size_bytes or 1
            progress(terminal, terminal)
        return saved

    def verify(
        self,
        project_id: str,
        progress: ProgressCallback | None = None,
    ) -> RecoveryEvidenceRecord:
        record = self.load(project_id)
        if record is None:
            raise ProjectError("Register recovery evidence before verification")
        result = record
        roles = tuple(
            role
            for role in ("external_backup", "stock_recovery")
            if getattr(record, role) is not None
        )
        targets = []
        total_bytes = 0
        for role in roles:
            artifact = getattr(result, role)
            if artifact is None:
                continue
            path = self._located_file(project_id, role, artifact)
            targets.append((role, artifact, path))
            total_bytes += path.stat().st_size

        completed_bytes = 0
        for role, artifact, path in targets:
            base = completed_bytes

            def publish_hash(done: int, _total: int, *, offset: int = base) -> None:
                combined = offset + done
                if progress is not None and total_bytes > 0 and combined < total_bytes:
                    progress(combined, total_bytes)

            digest = _sha256(
                path,
                publish_hash,
            )
            stat = path.stat()
            if digest != artifact.sha256 or stat.st_size != artifact.size_bytes:
                raise ProjectError(f"{_role_label(role)} no longer matches its recorded SHA-256")
            refreshed = replace(
                artifact,
                modified_ns=stat.st_mtime_ns,
                verified_at=datetime.now(UTC).isoformat(),
            )
            result = replace(result, **{role: refreshed})
            completed_bytes += stat.st_size
        result = replace(result, updated_at=datetime.now(UTC).isoformat())
        result = self._save(project_id, result, self._load_locators(project_id))
        if progress is not None:
            terminal = total_bytes or 1
            progress(terminal, terminal)
        return result

    def assess(
        self,
        project_id: str,
        device: AndroidDevice | None = None,
    ) -> RecoveryEvidenceAssessment:
        record = self.load(project_id)
        if record is None:
            return RecoveryEvidenceAssessment(
                False,
                False,
                False,
                (
                    "External phone backup is not registered",
                    "Exact stock-recovery package is not registered",
                ),
            )
        if record.schema_version != 2:
            return RecoveryEvidenceAssessment(
                False,
                False,
                False,
                (
                    "Legacy recovery evidence is preserved but must be fully verified again",
                    "Open Time Machine and choose Verify evidence to upgrade this project safely",
                ),
            )
        results: dict[str, bool] = {}
        details = []
        for role in ("external_backup", "stock_recovery"):
            artifact = getattr(record, role)
            ready = False
            detail = "missing or changed; register and verify again"
            if artifact is not None:
                try:
                    path = self._located_file(project_id, role, artifact)
                    stat = path.stat()
                    ready = (
                        stat.st_size == artifact.size_bytes
                        and stat.st_mtime_ns == artifact.modified_ns
                    )
                except (OSError, ProjectError):
                    ready = False
                if ready:
                    detail = f"verified {artifact.sha256[:16]}…"
                    if role == "external_backup" and artifact.provenance == "romverse-phone-media":
                        if device is not None:
                            current_key = (
                                WorkspacePrivacy(self.store.workspace).pseudonym(device.serial)
                                if device.state is DeviceState.DEVICE and device.serial
                                else ""
                            )
                            if artifact.device_key != current_key:
                                ready = False
                                detail = (
                                    "verified archive belongs to a different phone; create or register "
                                    "a backup for the exact connected device"
                                )
                            else:
                                detail += " • exact connected phone bound"
                        else:
                            detail += " • ROMVERSE device binding recorded"
            results[role] = ready
            details.append(f"{_role_label(role)}: {detail}")
        ready = results["external_backup"] and results["stock_recovery"]
        return RecoveryEvidenceAssessment(
            ready,
            results["external_backup"],
            results["stock_recovery"],
            tuple(details),
        )

    def load(self, project_id: str) -> RecoveryEvidenceRecord | None:
        project = self.store.get(project_id)
        path = self.store.projects_root / project_id / self.RECEIPT_NAME
        try:
            data = read_json_object(
                path,
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_RECEIPT_BYTES,
            )
            schema_version = data.get("schema_version")
            record_fields = {field.name for field in fields(RecoveryEvidenceRecord)}
            if schema_version == 1:
                record_fields.remove("record_digest")
            if (
                set(data) != {"format", *record_fields}
                or data.pop("format") != "romverse.recovery-evidence"
            ):
                return None
            backup_data = data.pop("external_backup")
            recovery_data = data.pop("stock_recovery")
            artifact_fields = {field.name for field in fields(RecoveryArtifactEvidence)}
            if any(
                item is not None and (not isinstance(item, dict) or set(item) != artifact_fields)
                for item in (backup_data, recovery_data)
            ):
                return None
            record = RecoveryEvidenceRecord(
                **data,
                external_backup=(
                    RecoveryArtifactEvidence(**backup_data) if backup_data is not None else None
                ),
                stock_recovery=(
                    RecoveryArtifactEvidence(**recovery_data) if recovery_data is not None else None
                ),
            )
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            return None
        source_sha256 = project.original.sha256 if project.original else ""
        values = asdict(record)
        record_digest = str(values.pop("record_digest"))
        if (
            record.schema_version not in {1, 2}
            or record.project_id != project_id
            or record.device_pack_id != project.device_pack_id
            or record.source_original_sha256 != source_sha256
            or not _sha256_value(record.source_original_sha256)
            or type(record.phone_changed) is not bool
            or record.phone_changed
            or not _aware_timestamp(record.created_at)
            or not _aware_timestamp(record.updated_at)
            or (record.external_backup is None and record.stock_recovery is None)
            or (
                record.external_backup is not None
                and not _valid_artifact_metadata(record.external_backup, "external_backup")
            )
            or (
                record.stock_recovery is not None
                and (
                    not _valid_artifact_metadata(record.stock_recovery, "stock_recovery")
                    or record.stock_recovery.sha256 != source_sha256
                )
            )
            or (
                record.schema_version == 2
                and (not _sha256_value(record_digest) or record_digest != _digest(values))
            )
            or (record.schema_version == 1 and record_digest)
        ):
            return None
        return record

    def _located_file(
        self,
        project_id: str,
        role: str,
        artifact: RecoveryArtifactEvidence,
    ) -> Path:
        raw = self._load_locators(project_id).get(role, "")
        if not raw or "\x00" in raw:
            raise ProjectError(f"{_role_label(role)} location is unavailable")
        unresolved = Path(raw).expanduser()
        if unresolved.is_symlink():
            raise ProjectError(f"{_role_label(role)} cannot be a symbolic link")
        try:
            path = unresolved.resolve(strict=True)
        except OSError as exc:
            raise ProjectError(f"{_role_label(role)} file is unavailable") from exc
        if (
            path.is_relative_to(self.store.workspace.resolve())
            or not path.is_file()
            or path.name != artifact.display_name
        ):
            raise ProjectError(f"{_role_label(role)} identity changed")
        return path

    def _load_locators(self, project_id: str) -> dict[str, str]:
        path = self.store.projects_root / project_id / self.LOCATOR_NAME
        try:
            payload = read_json_object(
                path,
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_LOCATOR_BYTES,
            )
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return {}
        if (
            set(payload) != {"format", "schema_version", "project_id", "locators"}
            or payload.get("format") != "romverse.private-locators"
            or payload.get("schema_version") != 1
            or payload.get("project_id") != project_id
        ):
            return {}
        locators = payload.get("locators")
        if (
            not isinstance(locators, dict)
            or len(locators) > len(self.ROLES)
            or any(
                role not in self.ROLES or not _valid_locator(value)
                for role, value in locators.items()
            )
        ):
            return {}
        return {str(role): str(value) for role, value in locators.items()}

    def _save(
        self,
        project_id: str,
        record: RecoveryEvidenceRecord,
        locators: dict[str, str],
    ) -> RecoveryEvidenceRecord:
        project = self.store.get(project_id)
        source_sha256 = project.original.sha256 if project.original else ""
        expected_locators = {role for role in self.ROLES if getattr(record, role) is not None}
        if (
            record.project_id != project_id
            or record.device_pack_id != project.device_pack_id
            or record.source_original_sha256 != source_sha256
            or not _sha256_value(source_sha256)
            or record.phone_changed
            or (
                record.external_backup is not None
                and not _valid_artifact_metadata(record.external_backup, "external_backup")
            )
            or (
                record.stock_recovery is not None
                and (
                    not _valid_artifact_metadata(record.stock_recovery, "stock_recovery")
                    or record.stock_recovery.sha256 != source_sha256
                )
            )
            or set(locators) != expected_locators
            or any(
                role not in self.ROLES or not _valid_locator(value)
                for role, value in locators.items()
            )
        ):
            raise ProjectError("Recovery evidence contains an unsafe project locator")
        normalized = replace(record, schema_version=2, record_digest="")
        values = asdict(normalized)
        values.pop("record_digest")
        normalized = replace(normalized, record_digest=_digest(values))
        root = self.store.projects_root / project_id
        locator_path = root / self.LOCATOR_NAME
        atomic_write_json(
            locator_path,
            {
                "format": "romverse.private-locators",
                "schema_version": 1,
                "project_id": project_id,
                "locators": locators,
            },
            boundary=self.store.workspace,
            maximum_bytes=self.MAX_LOCATOR_BYTES,
        )
        atomic_write_json(
            root / self.RECEIPT_NAME,
            {"format": "romverse.recovery-evidence", **asdict(normalized)},
            boundary=self.store.workspace,
            maximum_bytes=self.MAX_RECEIPT_BYTES,
        )
        return normalized


def _role_label(role: str) -> str:
    return "External phone backup" if role == "external_backup" else "Stock recovery package"


def _valid_artifact_metadata(
    artifact: RecoveryArtifactEvidence,
    expected_role: str,
) -> bool:
    base_valid = bool(
        artifact.role == expected_role
        and _display_name(artifact.display_name)
        and type(artifact.size_bytes) is int
        and 0 < artifact.size_bytes <= RecoveryEvidenceService.MAX_ARTIFACT_BYTES
        and type(artifact.modified_ns) is int
        and artifact.modified_ns > 0
        and _sha256_value(artifact.sha256)
        and _aware_timestamp(artifact.verified_at)
    )
    if not base_valid:
        return False
    if artifact.provenance == "external-file":
        return (
            not artifact.device_key and not artifact.coverage and not artifact.source_receipt_digest
        )
    return bool(
        expected_role == "external_backup"
        and artifact.provenance == "romverse-phone-media"
        and re.fullmatch(r"[0-9a-f]{20}", artifact.device_key)
        and artifact.coverage == "user-accessible shared storage only"
        and _sha256_value(artifact.source_receipt_digest)
    )


def _sha256(path: Path, progress: ProgressCallback | None = None) -> str:
    digest = hashlib.sha256()
    total = path.stat().st_size
    read = 0
    with path.open("rb") as stream:
        while chunk := stream.read(RecoveryEvidenceService.CHUNK_SIZE):
            digest.update(chunk)
            read += len(chunk)
            if progress is not None:
                progress(read, total)
    return digest.hexdigest()


def _digest(payload: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
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


def _display_name(value: object) -> bool:
    return bool(
        isinstance(value, str)
        and 1 <= len(value) <= 255
        and value not in {".", ".."}
        and Path(value).name == value
        and "\x00" not in value
    )


def _valid_locator(value: object) -> bool:
    return bool(
        isinstance(value, str)
        and 1 <= len(value) <= 4_096
        and "\x00" not in value
        and Path(value).is_absolute()
    )
